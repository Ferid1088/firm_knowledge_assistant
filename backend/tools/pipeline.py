"""Full ingest pipeline — 12 steps.

0️⃣  Read                    FileReaderTool dispatched by extension (Tool Registry)
1️⃣  Scan check              SAME for all (PDFs may be scanned)
2️⃣  Type resolution         SAME for all (user-selection > LLM-on-sample)
3️⃣  Parse                   DIFFERENT per type  (Docling | OCR | EML)
4️⃣  Chunk                   DIFFERENT per type  (9 chunker strategies)
5️⃣  Page sizes              SAME for all
6️⃣  Lang detect             SAME for all
7️⃣  BM25 build              SAME for all  (sparse vectors per language)
8️⃣  Enrich embed text       LLM descriptions for oversize tables + figures
9️⃣  Embed                   Qwen3-Embedding on enriched context_text
🔟 Quality gate            SAME for all  (size + text check)
1️⃣1️⃣ Store                  SAME for all  (Qdrant, is_current versioning)

Returns IngestResult with chunk count, resolved doc_type, and scan info.
"""
from __future__ import annotations
import sys
from dataclasses import dataclass
from pathlib import Path

from backend.config import QDRANT_DIR, EMBED_MODEL_ID
from backend.tools.parse import store_original
from backend.tools.readers import (  # noqa: F401 — side-effect: registers tools
    PDFReaderTool, DOCXReaderTool, XLSXReaderTool, CSVReaderTool,
    TextReaderTool, EMLReaderTool, ImageReaderTool,
)
from backend.tools.scan_detector import detect_scan
from backend.tools.type_detector import detect_type
from backend.tools.type_registry import get_handler, handler_info
from backend.services.citations import page_sizes, chunk_address
from backend.adapters.embedder import load_embedder, token_count
from backend.services.sparse import BM25Index
from backend.services.store import get_collection, index_chunks
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
    """Run the full 12-step ingestion pipeline (steps 0–11).

    doc_type_id: admin-defined document type ID; when None, auto-detected.
    department_ids: list of department IDs the document belongs to; stamped
                    onto every chunk's metadata and Qdrant payload.
    """
    pdf_path = str(Path(pdf_path).resolve())
    doc_id = Path(pdf_path).stem

    # ── Step 0: Reader dispatch (Tool Registry) ───────────────────────────────
    # Pre-check: if a reader is registered for this extension, run it to detect
    # corruption early and log file metadata. Readers whose dependencies are not
    # installed are never registered (hard ImportError at instantiation), so
    # _get_reader() simply returns None and we skip the pre-check cleanly.
    if verbose:
        print(f"[0/11 read]   {Path(pdf_path).suffix.lower()} via Tool Registry")
    reader = _get_reader(pdf_path)
    if reader is None:
        if verbose:
            print(f"            no reader registered for '{Path(pdf_path).suffix}' — skipping pre-check")
    else:
        try:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError("closed")
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            raw = loop.run_until_complete(reader.execute(pdf_path))
            if raw.is_corrupted:
                raise RuntimeError(
                    f"File could not be read ({reader.metadata.name}): "
                    + "; ".join(raw.warnings)
                )
            if verbose:
                print(f"            reader={reader.metadata.name}  "
                      f"size={raw.file_size}B  confidence={raw.extraction_confidence:.2f}")
        except RuntimeError:
            raise  # genuine file corruption — propagate
        except Exception as pre_err:
            if verbose:
                print(f"            [WARN] reader pre-check failed: {pre_err}")

    # ── Step 1: Scan check ────────────────────────────────────────────────────
    if verbose:
        print(f"[1/11 scan]   {pdf_path}")
    scan = detect_scan(pdf_path)

    if scan.is_scanned and doc_type_id != "scanned_image":
        print(
            f"[WARN]  PDF appears SCANNED ({scan.scanned_ratio:.0%} empty pages). "
            f"Quarantined. Empty pages: {scan.empty_pages}"
        )
        return IngestResult(
            n_chunks=0,
            doc_type=doc_type_id or "scanned_image",
            doc_type_confidence=0.0,
            is_scanned=True,
            empty_pages=scan.empty_pages,
        )
    if scan.empty_pages:
        print(f"[WARN]  pages without text layer (excluded): {scan.empty_pages}")

    # ── Step 2: Type resolution ───────────────────────────────────────────────
    if doc_type_id:
        resolved_type = doc_type_id
        type_confidence = 1.0
        if verbose:
            print(f"[2/11 type]   user-selected: {resolved_type}")
    else:
        if verbose:
            print("[2/11 type]   auto-detecting …")
        tr = detect_type(pdf_path)
        resolved_type = tr.doc_type
        type_confidence = tr.confidence
        if verbose:
            print(f"[2/11 type]   → {resolved_type} (conf={type_confidence:.2f})")

    handler = get_handler(resolved_type)
    info = handler_info(resolved_type)
    if verbose:
        print(f"            parser={info['parser']}  chunker={info['chunker']}  "
              f"embed={info['embed_strategy']}")

    # ── Step 3: Parse ─────────────────────────────────────────────────────────
    if verbose:
        print(f"[3/11 parse]  {info['parser']}")
    try:
        parse_result = handler.parse(pdf_path)
    except Exception as e:
        raise RuntimeError(
            f"Parser '{info['parser']}' failed for doc_type='{resolved_type}': {e}"
        ) from e

    store_original(pdf_path, doc_id)

    # ── Step 4: Chunk ─────────────────────────────────────────────────────────
    if verbose:
        print(f"[4/11 chunk]  {info['chunker']}")
    try:
        chunks = handler.chunk(parse_result)
    except Exception as e:
        raise RuntimeError(
            f"Chunker '{info['chunker']}' failed for doc_type='{resolved_type}': {e}"
        ) from e

    leaf_chunks = [c for c in chunks if c.is_leaf]

    # Stamp semantic_type (doc_type), structural_type, embed_strategy, department_ids
    _dept_ids = department_ids or []
    from backend.tools.chunk import classify_table_role
    _table_schemas = handler.table_schemas
    for ch in chunks:
        ch.metadata.setdefault("doc_type", resolved_type)
        ch.metadata.setdefault("doc_type_id", doc_type_id or resolved_type)
        ch.metadata.setdefault("embed_strategy", info["embed_strategy"])
        ch.metadata["department_ids"] = _dept_ids
        # structural_type mirrors chunk_type for dual-label querying per adaptive spec
        ch.metadata["structural_type"] = ch.chunk_type
        # classify table role using doc-type-specific keyword schemas
        if ch.chunk_type == "table":
            headers = ch.metadata.get("table_structure", {}).get("headers", [])
            ch.metadata["table_role"] = classify_table_role(headers, _table_schemas)

    if verbose:
        print(f"            {len(chunks)} total chunks ({len(leaf_chunks)} leaves)")

    # ── Step 5: Page sizes ────────────────────────────────────────────────────
    if verbose:
        print("[5/11 sizes]  bbox normalization")
    sizes = page_sizes(pdf_path)

    # ── Step 6: Language detection ────────────────────────────────────────────
    if verbose:
        print("[6/11 lang]   per-chunk detection")
    for ch in leaf_chunks:
        ch.metadata["lang"] = _detect_lang(ch.text)

    # ── Step 7: BM25 sparse vectors ───────────────────────────────────────────
    if verbose:
        print("[7/11 bm25]   building sparse indices")
    bm25_indices: dict[str, BM25Index] = {}
    for ld in registry.all():
        lang_chunks = [c for c in leaf_chunks if c.metadata.get("lang") == ld.code]
        if lang_chunks:
            idx = BM25Index(lang=ld.code)
            idx.add_documents([c.context_text for c in lang_chunks])
            bm25_indices[ld.code] = idx

    # ── Step 8: Enrich embed text ───────────────────────────────────────────
    if verbose:
        print(f"[8/11 enrich] embed text enrichment ({info['embed_strategy']})")
    _enrich_embed_texts(leaf_chunks, verbose)

    # ── Step 9: Embed ─────────────────────────────────────────────────────────
    if verbose:
        print(f"[9/11 embed]  {info['embed_strategy']} via {EMBED_MODEL_ID}")
    embedder = load_embedder()

    if verbose:
        for i, ch in enumerate(leaf_chunks):
            toks = token_count(embedder, ch.context_text)
            heads = " > ".join(ch.heading_path) if ch.heading_path else "(no heading)"
            addr = chunk_address(ch, doc_id, sizes)
            page = addr.get("page") or "?"
            print(f"  [{i:03d}] {ch.chunk_type:16s} page={page} "
                  f"lang={ch.metadata.get('lang','?')} tokens={toks:4d}  {heads[:55]}")

    # ── Step 10: Quality gate ─────────────────────────────────────────────────
    if verbose:
        print("[10/11 gate]  filtering low-quality chunks")
    before = len(leaf_chunks)
    leaf_chunks = [
        c for c in leaf_chunks
        if len(c.text.strip()) >= 10          # minimum text
        and c.context_text.strip()             # must have embedding text
    ]
    dropped = before - len(leaf_chunks)
    if dropped and verbose:
        print(f"            dropped {dropped} under-threshold chunks")

    # ── Step 11: Store ────────────────────────────────────────────────────────
    if verbose:
        print("[11/11 store] → Qdrant")
    collection_tuple = get_collection(persist_dir)
    n = index_chunks(collection_tuple, leaf_chunks, embedder, bm25_indices, doc_id, sizes)
    if verbose:
        print(f"            indexed {n} chunks "
              f"(doc_type={resolved_type}, chunker={info['chunker']}) → {persist_dir}")

    return IngestResult(
        n_chunks=n,
        doc_type=resolved_type,
        doc_type_confidence=type_confidence,
        is_scanned=False,
        empty_pages=scan.empty_pages,
        parser_name=info["parser"],
        chunker_name=info["chunker"],
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
