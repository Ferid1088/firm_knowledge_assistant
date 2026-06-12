"""Node: retrieve — bidirectional hybrid fan-out with RRF fusion."""
from __future__ import annotations

from backend.config import ENABLE_TRANSLATED_BM25
from backend.graph.state import RAGState
from backend.graph.utils import retrieve_pool_size
from backend.services.model_registry import get_embedder, get_collection, get_bm25_indices
from backend.services.fusion import rrf_fuse_hits


def retrieve(state: RAGState) -> RAGState:
    from backend.services.store import search as store_search

    sub_questions = state.get("sub_questions", [state["question"]])
    active_codes = state.get("active_lang_codes", ["de"])
    translated = state.get("translated_queries", {})
    attempts = state.get("attempts", 0)
    k = retrieve_pool_size(attempts)

    collection = get_collection()
    embedder = get_embedder()
    bm25 = get_bm25_indices()

    all_hits: list[dict] = []
    seen_ids: set[str] = set()

    for sub_q in sub_questions:
        hits = store_search(collection, embedder, sub_q, bm25, active_codes, k=k)
        for h in hits:
            cid = h["chunk_id"]
            if cid not in seen_ids:
                seen_ids.add(cid)
                all_hits.append(h)

    if ENABLE_TRANSLATED_BM25:
        for lang_code, trans_q in translated.items():
            if trans_q == sub_questions[0]:
                continue
            hits = store_search(collection, embedder, trans_q, bm25, [lang_code], k=k // 2)
            for h in hits:
                cid = h["chunk_id"]
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    all_hits.append(h)

    all_hits.sort(key=lambda x: x["score"], reverse=True)
    all_hits = all_hits[:k]

    rewritten_query = state.get("rewritten_query", "")
    if rewritten_query:
        rewrite_hits = store_search(collection, embedder, rewritten_query, bm25, active_codes, k=k)
        all_hits = rrf_fuse_hits([all_hits, rewrite_hits])[:k]

    return {**state, "candidate_pool": all_hits, "effective_retrieve_k": k}
