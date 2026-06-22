"""Node: rerank — Qwen3-Reranker scores the deep pool down to RERANKER_TOP_K."""
from __future__ import annotations

import logging

from backend.config import RERANKER_TOP_K
from backend.graph.retrieval.state import RAGState
from backend.graph.retrieval.utils import get_reranker

log = logging.getLogger("retrieval.rerank")


def rerank(state: RAGState) -> RAGState:
    """Score the candidate pool with Qwen3-Reranker and keep the top RERANKER_TOP_K hits."""
    pool = state.get("candidate_pool", [])
    if not pool:
        return {**state, "reranked": []}

    question = state["question"]
    reranker = get_reranker()

    pairs = [(question, h["context_text"]) for h in pool]
    try:
        scores = reranker.predict(pairs)
        ranked = sorted(zip(pool, scores), key=lambda x: x[1], reverse=True)
        reranked = []
        for hit, score in ranked[:RERANKER_TOP_K]:
            reranked.append({**hit, "rerank_score": float(score)})
        return {**state, "reranked": reranked, "reranker_failed": False}
    except Exception:
        log.warning(
            "Reranker failed for query '%s' (pool size=%d); falling back to retrieval order",
            question[:80], len(pool), exc_info=True,
        )
        reranked = pool[:RERANKER_TOP_K]
        return {**state, "reranked": reranked, "reranker_failed": True}
