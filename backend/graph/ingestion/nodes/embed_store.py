"""Node: embed_store — embed leaf chunks and store in Qdrant."""
from __future__ import annotations

import logging
from pathlib import Path

from backend.config import QDRANT_DIR
from backend.graph.ingestion.state import IngestionState

log = logging.getLogger("ingestion")


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
