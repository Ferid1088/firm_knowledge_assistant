"""Node: rerank — Qwen3-Reranker cross-encoder scoring."""
from __future__ import annotations

from backend.graph.state import RAGState
from backend.graph.utils import answer_source_limit
from backend.services.model_registry import get_reranker


def rerank(state: RAGState) -> RAGState:
    pool = state.get("candidate_pool", [])
    if not pool:
        return {**state, "reranked": []}

    question = state["question"]
    reranker = get_reranker()
    answer_k = min(len(pool), answer_source_limit(state.get("attempts", 0)))

    pairs = [(question, h["context_text"]) for h in pool]
    try:
        scores = reranker.predict(pairs)
        ranked = sorted(zip(pool, scores), key=lambda x: x[1], reverse=True)
        reranked = [{**hit, "rerank_score": float(score)} for hit, score in ranked[:answer_k]]
    except Exception:
        reranked = pool[:answer_k]

    return {**state, "reranked": reranked}
