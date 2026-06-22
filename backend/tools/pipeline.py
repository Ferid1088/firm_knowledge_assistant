"""Ingest pipeline — thin wrapper around the LangGraph ingestion graph.

The actual pipeline logic (triage, parse, chunk, embed, store) lives in
backend/graph/ingestion_graph.py.  This module keeps the backward-compatible
``ingest()`` entry-point, the ``IngestResult`` dataclass, and helpers that
the graph nodes import (_detect_lang, _enrich_embed_texts, _get_reader).

``rebuild_bm25_indices()`` is also here — the API still calls it directly.
"""
from __future__ import annotations
import sys
from dataclasses import dataclass
from pathlib import Path

from backend.config import QDRANT_DIR
from backend.tools.readers import (  # noqa: F401 — side-effect: registers tools
    PDFReaderTool, DOCXReaderTool, XLSXReaderTool, CSVReaderTool,
    TextReaderTool, EMLReaderTool, ImageReaderTool,
)
from backend.services.sparse import BM25Index
from backend.services.store import get_collection
from backend.services.language import registry


# ── Reader dispatch ────────────────────────────────────────────────────────────

def _get_reader(file_path: str):
    """Return the registered FileReaderTool for the given file extension, or None."""
    from backend.core.tool_registry import get_registry as _reg
    ext = Path(file_path).suffix.lower()
    reg = _reg()
    for meta in reg.list_tools(tool_type="reader"):
        formats = [f.lower() for f in meta.get("capabilities", {}).get("formats", [])]
        if ext in formats:
            return reg.get_tool(meta["name"])
    return None


# ── Result ─────────────────────────────────────────────────────────────────────

@dataclass
class IngestResult:
    """Summary returned by the full ingest pipeline for a single document."""

    n_chunks: int
    doc_type: str
    doc_type_confidence: float
    is_scanned: bool
    empty_pages: list[int]
    parser_name: str = ""
    chunker_name: str = ""


# ── Language detection ─────────────────────────────────────────────────────────

def _detect_lang(text: str) -> str:
    """Detect ISO-639-1 language code of text; maps unknown codes to 'de'."""
    try:
        from langdetect import detect
        lang_map = {"de": "de", "en": "en", "fr": "fr", "es": "es"}
        return lang_map.get(detect(text), "de")
    except Exception:
        return "de"


# ── Embed text enrichment (description_dense + figure descriptions) ───────────

def _llm_describe(prompt: str) -> str:
    """Call the local Ollama LLM to generate a short description."""
    import json
    import urllib.request
    from backend.config import OLLAMA_MODEL, OLLAMA_BASE_URL
    payload = json.dumps({
        "model": OLLAMA_MODEL, "prompt": prompt,
        "stream": False, "options": {"temperature": 0, "num_predict": 150},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()).get("response", "").strip()
    except Exception:
        return ""


def _build_enrichment_prompt(ch) -> str | None:
    """Return an LLM prompt for a chunk that needs enrichment, or None to skip."""
    from backend.config import OVERSIZE_EMBED_THRESHOLD
    from backend.tools.chunk import token_len

    heading = " > ".join(ch.heading_path) if ch.heading_path else ""

    if ch.chunk_type == "table" and token_len(ch.context_text) > OVERSIZE_EMBED_THRESHOLD:
        tbl = ch.metadata.get("table_structure", {})
        headers = tbl.get("headers", [])
        return (
            f"Describe this table in 1-2 sentences for search indexing.\n"
            f"Section: {heading}\n"
            f"Caption: {ch.metadata.get('caption', '')}\n"
            f"Headers: {', '.join(headers[:15])}\n"
            f"Rows: {tbl.get('n_rows', '?')}\n"
            f"First rows:\n{ch.text[:500]}\n\nDescription:"
        )

    if ch.chunk_type == "figure" and ch.metadata.get("needs_description"):
        return (
            f"Describe what this figure likely shows based on its context, in 1-2 sentences.\n"
            f"Section: {heading}\n"
            f"Caption: {ch.metadata.get('caption', '')}\n\nDescription:"
        )

    return None


def _apply_enrichment(ch, desc: str) -> None:
    """Apply an LLM-generated description to a chunk's embed text."""
    heading = " > ".join(ch.heading_path) if ch.heading_path else ""
    ch.metadata["embed_description"] = desc
    ch.context_text = f"{heading}\n\n{desc}" if heading else desc
    if ch.chunk_type == "figure":
        ch.metadata["needs_description"] = False


def _enrich_embed_texts(chunks: list, verbose: bool = False) -> None:
    """Enrich context_text for chunks that benefit from LLM-generated descriptions.

    Gated by ENABLE_EMBED_ENRICHMENT config flag. Uses ThreadPoolExecutor for
    parallel Ollama calls. Original text is always preserved.
    """
    from backend.config import ENABLE_EMBED_ENRICHMENT
    if not ENABLE_EMBED_ENRICHMENT:
        if verbose:
            print("            enrichment disabled (ENABLE_EMBED_ENRICHMENT=False)")
        return

    candidates = []
    for ch in chunks:
        prompt = _build_enrichment_prompt(ch)
        if prompt:
            candidates.append((ch, prompt))

    if not candidates:
        return

    if verbose:
        print(f"            enriching {len(candidates)} chunks via Ollama…")

    from concurrent.futures import ThreadPoolExecutor, as_completed
    results: dict[int, str] = {}

    with ThreadPoolExecutor(max_workers=min(4, len(candidates))) as pool:
        futures = {pool.submit(_llm_describe, prompt): i
                   for i, (_, prompt) in enumerate(candidates)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception:
                results[idx] = ""

    enriched = 0
    for i, (ch, _) in enumerate(candidates):
        desc = results.get(i, "")
        if desc:
            _apply_enrichment(ch, desc)
            enriched += 1

    if verbose and enriched:
        print(f"            enriched {enriched}/{len(candidates)} chunks with LLM descriptions")


# ── Pipeline ───────────────────────────────────────────────────────────────────

def ingest(
    pdf_path: str,
    persist_dir: str = QDRANT_DIR,
    verbose: bool = True,
    doc_type_id: str | None = None,
    department_ids: list[str] | None = None,
) -> IngestResult:
    """Run the LangGraph ingestion pipeline and return an IngestResult.

    This is the backward-compatible wrapper.  The actual pipeline logic
    is in backend/graph/ingestion_graph.py.
    """
    from backend.graph.ingestion_graph import run_ingest

    state = run_ingest(
        source_path=pdf_path,
        persist_dir=persist_dir,
        verbose=verbose,
        doc_type_id=doc_type_id,
        department_ids=department_ids,
    )

    if state.get("error"):
        raise RuntimeError(state["error"])

    return IngestResult(
        n_chunks=state.get("n_chunks", 0),
        doc_type=state.get("resolved_type", doc_type_id or "unknown"),
        doc_type_confidence=state.get("type_confidence", 0.0),
        is_scanned=state.get("is_scanned_result", False),
        empty_pages=state.get("empty_pages", []),
        parser_name=state.get("parser_name"),
        chunker_name=state.get("chunker_name"),
    )


# ── BM25 rebuild (query-time; unchanged) ──────────────────────────────────────

def rebuild_bm25_indices(persist_dir: str = QDRANT_DIR) -> dict[str, BM25Index]:
    """Rebuild per-language BM25 indices from all current chunks in the store."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client, collection = get_collection(persist_dir)
    texts_by_lang: dict[str, list[str]] = {}

    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(must=[FieldCondition(
                key="is_current", match=MatchValue(value=True)
            )]),
            limit=100,
            offset=offset,
            with_payload=True,
        )
        for p in points:
            lang = p.payload.get("lang", "de")
            texts_by_lang.setdefault(lang, []).append(p.payload.get("context_text", ""))
        if offset is None:
            break

    bm25_indices: dict[str, BM25Index] = {}
    for ld in registry.all():
        texts = texts_by_lang.get(ld.code)
        if texts:
            idx = BM25Index(lang=ld.code)
            idx.add_documents(texts)
            bm25_indices[ld.code] = idx
    return bm25_indices


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m backend.tools.pipeline <path/to/file.pdf> [doc_type]")
        sys.exit(1)
    dt = sys.argv[2] if len(sys.argv) > 2 else None
    ingest(sys.argv[1], doc_type_id=dt)
