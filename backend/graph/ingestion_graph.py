"""LangGraph ingestion pipeline — replaces the monolithic pipeline.ingest().

Flow:
    triage → [ocr_branch | text_parse] → detect_type → chunk → metadata
           → lang_detect → bm25 → enrich → embed_and_store

The OCR branch invokes the separate OCR subgraph (ocr_subgraph.py).
VLM enrichment (enrich node) is gated by ENABLE_VLM_ENRICHMENT config.
All existing parsers, chunkers, and store logic are reused as-is.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF — for triage text-layer check

from backend.config import (
    QDRANT_DIR, EMBED_MODEL_ID, ENABLE_VLM_ENRICHMENT,
    OCR_LANGS, OCR_BASE_IMAGES_SCALE,
)
from backend.graph.ingestion_state import IngestionState

log = logging.getLogger("ingestion")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


# ── Triage ──────────────────────────────────────────────────────────────────

def _has_text_layer(pdf_path: str, min_chars: int = 100) -> bool:
    try:
        with fitz.open(pdf_path) as doc:
            chars = sum(len(page.get_text("text")) for page in doc)
            return chars >= min_chars
    except Exception:
        return False


def triage_node(state: IngestionState) -> IngestionState:
    src = state["source_path"]
    suffix = Path(src).suffix.lower()

    if suffix in IMAGE_EXTENSIONS:
        return {**state, "is_scanned": True, "is_image": True}
    if suffix == ".pdf":
        return {**state, "is_scanned": not _has_text_layer(src), "is_image": False}
    return {**state, "is_scanned": False, "is_image": False}


def _route_after_triage(state: IngestionState) -> str:
    return "ocr" if state.get("is_scanned") else "text"


# ── Text parse (existing Docling path) ──────────────────────────────────────

def text_parse_node(state: IngestionState) -> IngestionState:
    from backend.tools.type_registry import get_handler
    from backend.tools.scan_detector import detect_scan
    from backend.tools.parse import store_original

    src = state["source_path"]
    doc_id = Path(src).stem
    verbose = state.get("verbose", True)

    # Scan check (belt-and-suspenders — triage already decided, but this
    # gives us empty_pages list for metadata)
    scan = detect_scan(src)
    if scan.empty_pages and verbose:
        log.warning("Pages without text layer: %s", scan.empty_pages)

    # Type detection
    doc_type_id = state.get("doc_type_id")
    if doc_type_id:
        resolved_type = doc_type_id
        type_confidence = 1.0
    else:
        from backend.tools.type_detector import detect_type
        tr = detect_type(src)
        resolved_type = tr.doc_type
        type_confidence = tr.confidence

    handler = get_handler(resolved_type)
    from backend.tools.type_registry import handler_info
    info = handler_info(resolved_type)
    if verbose:
        log.info("type=%s parser=%s chunker=%s", resolved_type, info["parser"], info["chunker"])

    # Parse
    parse_result = handler.parse(src)
    store_original(src, doc_id)

    return {
        **state,
        "doc_id": doc_id,
        "resolved_type": resolved_type,
        "type_confidence": type_confidence,
        "parse_result": parse_result,
        "empty_pages": scan.empty_pages,
        "parser_name": info["parser"],
        "chunker_name": info["chunker"],
        "is_scanned_result": False,
    }


# ── OCR branch (delegates to OCR subgraph) ─────────────────────────────────

def ocr_branch_node(state: IngestionState) -> IngestionState:
    from backend.graph.ocr_subgraph import build_ocr_subgraph

    ocr_graph = build_ocr_subgraph()
    sub_out = ocr_graph.invoke({
        "source_path": state["source_path"],
        "is_image": state.get("is_image", False),
        "ocr_lang": OCR_LANGS,
        "attempt": 0,
        "images_scale": OCR_BASE_IMAGES_SCALE,
    }, config={"recursion_limit": 10})

    doc_id = Path(state["source_path"]).stem
    from backend.tools.parse import store_original
    store_original(state["source_path"], doc_id)

    # After OCR, we still need type detection and chunking.
    # Use the OCR parse result but route through standard type detection.
    doc_type_id = state.get("doc_type_id")
    if doc_type_id:
        resolved_type = doc_type_id
        type_confidence = 1.0
    else:
        from backend.tools.type_detector import detect_type
        tr = detect_type(state["source_path"])
        resolved_type = tr.doc_type
        type_confidence = tr.confidence

    from backend.tools.type_registry import handler_info
    info = handler_info(resolved_type)

    return {
        **state,
        "doc_id": doc_id,
        "docling_doc": sub_out.get("docling_doc"),
        "resolved_type": resolved_type,
        "type_confidence": type_confidence,
        "parser_name": "OCR (" + sub_out.get("engine", "easyocr") + ")",
        "chunker_name": info["chunker"],
        "ocr_meta": {
            "engine": sub_out.get("engine", "easyocr"),
            "attempts": sub_out.get("attempt"),
            "low_confidence_pages": sub_out.get("low_confidence_pages", []),
            "total_pages": sub_out.get("total_pages", 0),
            "needs_review": sub_out.get("needs_review", False),
        },
        "empty_pages": sub_out.get("low_confidence_pages", []),
        "is_scanned_result": True,
    }


# ── Chunk ───────────────────────────────────────────────────────────────────

def chunk_node(state: IngestionState) -> IngestionState:
    from backend.tools.type_registry import get_handler
    from backend.tools.chunk import classify_table_role

    resolved_type = state["resolved_type"]
    handler = get_handler(resolved_type)

    if state.get("parse_result"):
        # Normal text path — parse_result from our parsers
        chunks = handler.chunk(state["parse_result"])
    elif state.get("docling_doc"):
        # OCR path — we have a DoclingDocument, need to wrap it
        from backend.tools.parsers.parse_result import ParseResult
        pr = ParseResult(
            doc=state["docling_doc"],
            empty_pages=state.get("empty_pages", []),
            parser_type="ocr",
            source_path=state["source_path"],
        )
        chunks = handler.chunk(pr)
    else:
        return {**state, "error": "No parse result or docling_doc in state"}

    leaf_chunks = [c for c in chunks if c.is_leaf]

    dept_ids = state.get("department_ids", [])
    doc_type_id = state.get("doc_type_id") or state.get("resolved_type")
    table_schemas = handler.table_schemas

    for ch in chunks:
        ch.metadata.setdefault("doc_type", resolved_type)
        ch.metadata.setdefault("doc_type_id", doc_type_id)
        ch.metadata["department_ids"] = dept_ids
        ch.metadata["structural_type"] = ch.chunk_type
        if ch.chunk_type == "table":
            headers = ch.metadata.get("table_structure", {}).get("headers", [])
            ch.metadata["table_role"] = classify_table_role(headers, table_schemas)

    # Propagate OCR review flag
    ocr_meta = state.get("ocr_meta")
    if ocr_meta and ocr_meta.get("needs_review"):
        for c in leaf_chunks:
            c.metadata["ocr_needs_review"] = True

    return {**state, "chunks": chunks, "leaf_chunks": leaf_chunks}


# ── Language detection ──────────────────────────────────────────────────────

def lang_detect_node(state: IngestionState) -> IngestionState:
    from backend.tools.pipeline import _detect_lang
    for ch in state.get("leaf_chunks", []):
        ch.metadata["lang"] = _detect_lang(ch.text)
    return state


# ── BM25 sparse vectors ────────────────────────────────────────────────────

def bm25_node(state: IngestionState) -> IngestionState:
    from backend.services.sparse import BM25Index
    from backend.services.language import registry

    bm25_indices: dict[str, BM25Index] = {}
    leaf_chunks = state.get("leaf_chunks", [])
    for ld in registry.all():
        lang_chunks = [c for c in leaf_chunks if c.metadata.get("lang") == ld.code]
        if lang_chunks:
            idx = BM25Index(lang=ld.code)
            idx.add_documents([c.context_text for c in lang_chunks])
            bm25_indices[ld.code] = idx
    return {**state, "bm25_indices": bm25_indices}


# ── Enrich (VLM — GPU only, no-op on pilot) ────────────────────────────────

def enrich_node(state: IngestionState) -> IngestionState:
    if not ENABLE_VLM_ENRICHMENT:
        # Pilot path: use existing Ollama-based enrichment
        from backend.tools.pipeline import _enrich_embed_texts
        _enrich_embed_texts(state.get("leaf_chunks", []), state.get("verbose", True))
        return state

    # GPU path: VLM enrichment would go here (Qwen3-VL)
    # Deferred — same structure as docs/graph_update/ingestion_graph.py enrich_node
    log.info("VLM enrichment enabled but not yet integrated — using Ollama fallback")
    from backend.tools.pipeline import _enrich_embed_texts
    _enrich_embed_texts(state.get("leaf_chunks", []), state.get("verbose", True))
    return state


# ── Quality gate ────────────────────────────────────────────────────────────

def quality_gate_node(state: IngestionState) -> IngestionState:
    leaf_chunks = state.get("leaf_chunks", [])
    before = len(leaf_chunks)
    filtered = [
        c for c in leaf_chunks
        if len(c.text.strip()) >= 10 and c.context_text.strip()
    ]
    dropped = before - len(filtered)
    if dropped:
        log.info("Quality gate: dropped %d/%d chunks", dropped, before)
    return {**state, "leaf_chunks": filtered}


# ── Embed and store ─────────────────────────────────────────────────────────

def embed_store_node(state: IngestionState) -> IngestionState:
    from backend.adapters.embedder import load_embedder
    from backend.services.store import get_collection, index_chunks
    from backend.services.citations import page_sizes

    persist_dir = state.get("persist_dir", QDRANT_DIR)
    leaf_chunks = state.get("leaf_chunks", [])
    doc_id = state.get("doc_id", Path(state["source_path"]).stem)

    embedder = load_embedder()
    sizes = page_sizes(state["source_path"])
    bm25_indices = state.get("bm25_indices", {})

    collection = get_collection(persist_dir)
    n = index_chunks(collection, leaf_chunks, embedder, bm25_indices, doc_id, sizes)

    log.info("Indexed %d chunks for %s", n, doc_id)
    return {**state, "n_chunks": n}


# ── Build the graph ─────────────────────────────────────────────────────────

def build_ingestion_graph():
    from langgraph.graph import StateGraph, START, END

    g = StateGraph(IngestionState)
    g.add_node("triage", triage_node)
    g.add_node("text_parse", text_parse_node)
    g.add_node("ocr_branch", ocr_branch_node)
    g.add_node("chunk", chunk_node)
    g.add_node("lang_detect", lang_detect_node)
    g.add_node("bm25", bm25_node)
    g.add_node("enrich", enrich_node)
    g.add_node("quality_gate", quality_gate_node)
    g.add_node("embed_store", embed_store_node)

    g.add_edge(START, "triage")
    g.add_conditional_edges(
        "triage", _route_after_triage,
        {"ocr": "ocr_branch", "text": "text_parse"},
    )
    g.add_edge("text_parse", "chunk")
    g.add_edge("ocr_branch", "chunk")
    g.add_edge("chunk", "lang_detect")
    g.add_edge("lang_detect", "bm25")
    g.add_edge("bm25", "enrich")
    g.add_edge("enrich", "quality_gate")
    g.add_edge("quality_gate", "embed_store")
    g.add_edge("embed_store", END)
    return g.compile()


# ── Public API ──────────────────────────────────────────────────────────────

_compiled_graph = None


def run_ingest(
    source_path: str,
    persist_dir: str = QDRANT_DIR,
    verbose: bool = True,
    doc_type_id: str | None = None,
    department_ids: list[str] | None = None,
) -> IngestionState:
    """Run the ingestion graph and return the final state."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_ingestion_graph()

    init: IngestionState = {
        "source_path": str(Path(source_path).resolve()),
        "doc_type_id": doc_type_id,
        "department_ids": department_ids or [],
        "verbose": verbose,
        "persist_dir": persist_dir,
    }
    return _compiled_graph.invoke(init)
