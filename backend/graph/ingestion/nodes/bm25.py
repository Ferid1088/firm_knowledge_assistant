"""Node: bm25 — build per-document BM25 sparse vectors for the current batch.

NOTE: These indices are scoped to the current document's chunks -- they
produce the sparse vectors stored per-point in Qdrant (used by
index_chunks in store.py).  The corpus-level BM25 statistics are rebuilt
separately via rebuild_bm25_indices() called after ingestion completes
in the API layer.  This is intentional: IDF statistics over the full
corpus cannot be computed inside a single-document ingestion run.
"""
from __future__ import annotations

from backend.graph.ingestion.state import IngestionState


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
