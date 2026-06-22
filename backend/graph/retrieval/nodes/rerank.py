"""Node: rerank — Qwen3-Reranker scores the deep pool down to RETRIEVE_K."""
from __future__ import annotations

from backend.config import RETRIEVE_K
from backend.graph.retrieval.state import RAGState
from backend.graph.retrieval.utils import get_reranker


def rerank(state: RAGState) -> RAGState:
    """Score the candidate pool with Qwen3-Reranker and keep the top RETRIEVE_K hits."""
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
        for hit, score in ranked[:RETRIEVE_K]:
            reranked.append({**hit, "rerank_score": float(score)})
    except Exception:
        # If reranker fails (e.g. not yet downloaded), fall back to retrieval order
        reranked = pool[:RETRIEVE_K]

    return {**state, "reranked": reranked}
