"""Full ingest pipeline: parse -> chunk -> detect lang -> embed -> BM25 -> store.

Run once per PDF. Re-ingesting the same doc supersedes the old version (is_current flag).
"""
from __future__ import annotations
import sys
from pathlib import Path

from config import QDRANT_DIR, EMBED_MODEL_ID, ORIGINALS_DIR, STRUCTURE, OLLAMA_MODEL
from src.ingest.parse import make_converter, parse_pdf, store_original
from src.ingest.chunk import chunk_document, make_prose_chunker
from src.structure import filter_empty_leaves, attach_references, merge_orphans_and_lists
from src.common.citations import page_sizes, chunk_address
from src.common.embed import load_embedder, token_count
from src.common.sparse import BM25Index, tokenize
from src.common.store import get_collection, index_chunks
from src.common.language import registry


def _detect_lang(text: str) -> str:
    try:
        from langdetect import detect
        lang = detect(text)
        # Map langdetect codes to our registry codes
        lang_map = {"de": "de", "en": "en", "fr": "fr", "es": "es"}
        return lang_map.get(lang, "de")
    except Exception:
        return "de"


def ingest(pdf_path: str, persist_dir: str = QDRANT_DIR, verbose: bool = True) -> int:
    pdf_path = str(Path(pdf_path).resolve())
    doc_id = Path(pdf_path).stem

    # ── Parse ──────────────────────────────────────────────────────────────
    if verbose:
        print(f"[parse]  {pdf_path}")
    converter = make_converter()
    doc, empty_pages = parse_pdf(pdf_path, converter)
    if empty_pages:
        print(f"[WARN]   pages with no text layer (quarantined from index): {empty_pages}")
    store_original(pdf_path, doc_id)

    # ── Chunk ──────────────────────────────────────────────────────────────
    prose_chunker = make_prose_chunker()
    structure_stats: dict = {}
    chunks = chunk_document(doc, prose_chunker, stats=structure_stats, doc_lang="de", ollama_model=OLLAMA_MODEL)
    chunks, n_dropped = filter_empty_leaves(chunks, STRUCTURE)
    chunks, n_merged = merge_orphans_and_lists(chunks, STRUCTURE)
    attach_references(chunks, STRUCTURE)
    leaf_chunks = [c for c in chunks if c.is_leaf]
    structure_stats["leaves_dropped"] = n_dropped
    structure_stats["orphans_lists_merged"] = n_merged
    structure_stats["final_leaves"] = len(leaf_chunks)
    if verbose:
        print(f"[chunk]  {len(chunks)} total ({len(leaf_chunks)} leaves, "
              f"{n_dropped} low-substance leaves dropped, {n_merged} orphans/list-items merged)")

    # ── Per-document quality metric (indexing_correction.md, step 9) ────────
    if verbose:
        print(
            f"[quality] doc_id={doc_id} "
            f"pseudo_headers_demoted={structure_stats['pseudo_headers_demoted']} "
            f"headers_flagged_ambiguous={structure_stats['headers_flagged_ambiguous']} "
            f"headers_llm_demoted={structure_stats['headers_llm_demoted']} "
            f"leaves_dropped={structure_stats['leaves_dropped']} "
            f"orphans_lists_merged={structure_stats['orphans_lists_merged']} "
            f"final_leaves={structure_stats['final_leaves']}"
        )

    # ── Page sizes for bbox normalization ──────────────────────────────────
    sizes = page_sizes(pdf_path)

    # ── Language detection per chunk ────────────────────────────────────────
    # Very short leaves inherit lang from the previous leaf (langdetect is
    # unreliable on short/meaningless text and would mis-route per-language BM25).
    lang_inherit_max = STRUCTURE.get("lang_inherit_max_chars", 0)
    prev_lang = registry.all()[0].code if registry.all() else "de"
    for ch in leaf_chunks:
        if len(ch.text.strip()) < lang_inherit_max:
            ch.metadata["lang"] = prev_lang
        else:
            ch.metadata["lang"] = _detect_lang(ch.text)
        prev_lang = ch.metadata["lang"]

    # ── Build BM25 indices per language ────────────────────────────────────
    bm25_indices: dict[str, BM25Index] = {}
    for ld in registry.all():
        lang_chunks = [c for c in leaf_chunks if c.metadata.get("lang") == ld.code]
        if lang_chunks:
            idx = BM25Index(lang=ld.code)
            idx.add_documents([c.context_text for c in lang_chunks])
            bm25_indices[ld.code] = idx

    # ── Embed ──────────────────────────────────────────────────────────────
    if verbose:
        print(f"[embed]  loading {EMBED_MODEL_ID} …")
    embedder = load_embedder()

    # ── Inspection dump (indexing_correction.md, step 9 — mandatory) ────────
    # First 50 chunks: text, chunk_type, heading_path, metadata — for review.
    if verbose:
        for i, ch in enumerate(leaf_chunks[:50]):
            toks = token_count(embedder, ch.context_text)
            heads = " > ".join(ch.heading_path) if ch.heading_path else "(no heading)"
            addr = chunk_address(ch, doc_id, sizes)
            page = addr.get("page") or "?"
            refs = ch.metadata.get("references") or []
            print(f"  [{i:03d}] {ch.chunk_type:14s} page={page} "
                  f"lang={ch.metadata.get('lang','?')} tokens={toks:4d} refs={refs}  {heads[:60]}")
            print(f"        text={ch.text[:100]!r}")
        if len(leaf_chunks) > 50:
            print(f"  ... ({len(leaf_chunks) - 50} more leaves not shown)")

    # ── Store ──────────────────────────────────────────────────────────────
    collection_tuple = get_collection(persist_dir)
    n = index_chunks(collection_tuple, leaf_chunks, embedder, bm25_indices, doc_id, sizes)
    if verbose:
        print(f"[store]  indexed {n} chunks -> {persist_dir}")
    return n


def rebuild_bm25_indices(persist_dir: str = QDRANT_DIR) -> dict[str, BM25Index]:
    """Rebuild per-language BM25 indices from all current chunks in the store.

    BM25 indices are not persisted with Qdrant; query-time sparse search needs
    them rebuilt from the stored context_text + lang payload of is_current chunks.
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client, collection = get_collection(persist_dir)
    bm25_indices: dict[str, BM25Index] = {}
    texts_by_lang: dict[str, list[str]] = {}

    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(must=[FieldCondition(key="is_current", match=MatchValue(value=True))]),
            limit=100,
            offset=offset,
            with_payload=True,
        )
        for p in points:
            lang = p.payload.get("lang", "de")
            texts_by_lang.setdefault(lang, []).append(p.payload.get("context_text", ""))
        if offset is None:
            break

    for ld in registry.all():
        texts = texts_by_lang.get(ld.code)
        if texts:
            idx = BM25Index(lang=ld.code)
            idx.add_documents(texts)
            bm25_indices[ld.code] = idx
    return bm25_indices


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.ingest.pipeline <path/to/file.pdf>")
        sys.exit(1)
    ingest(sys.argv[1])
