"""Lazy-loaded model singletons shared across graph nodes and ingest tools.

Import the getter, not the private variable:
    from backend.services.model_registry import get_embedder, get_reranker, get_collection, get_bm25_indices
"""
from __future__ import annotations

from backend.config import QDRANT_DIR, RERANKER_MODEL_ID

_embedder = None
_reranker = None
_collection_tuple = None
_bm25_indices: dict = {}


def get_embedder():
    global _embedder
    if _embedder is None:
        from backend.adapters.embedder import load_embedder
        _embedder = load_embedder()
    return _embedder


def get_reranker():
    global _reranker
    if _reranker is None:
        from backend.adapters.reranker import Qwen3Reranker
        _reranker = Qwen3Reranker(RERANKER_MODEL_ID, device="cpu")
    return _reranker


def get_collection():
    global _collection_tuple
    if _collection_tuple is None:
        from backend.services.store import get_collection as _get
        _collection_tuple = _get(QDRANT_DIR)
    return _collection_tuple


def get_bm25_indices() -> dict:
    return _bm25_indices


def set_bm25_indices(indices: dict) -> None:
    global _bm25_indices
    _bm25_indices = indices
