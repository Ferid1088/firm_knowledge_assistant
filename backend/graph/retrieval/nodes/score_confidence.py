"""Node: score_confidence — top-1 score, gap-to-tail, and best-across-loops tracking."""
from __future__ import annotations

from backend.graph.retrieval.state import RAGState


def score_confidence(state: RAGState) -> RAGState:
    """Compute top-1 reranker score and gap-to-tail for the router's confidence gate.

    Also tracks the best reranked results across all escalation iterations.
    If the current attempt scores higher than any previous attempt, update
    best_reranked and best_confidence. This ensures the answer/abstain node
    always uses the highest-scoring results, not just the last iteration's.
    """
    reranked = state.get("reranked", [])
    if not reranked:
        return {**state, "confidence": 0.0, "confidence_gap": 0.0}

    scores = [h.get("rerank_score", h.get("score", 0.0)) for h in reranked]
    top = scores[0]
    gap = top - scores[1] if len(scores) > 1 else top

    # Track best results across escalation loops
    prev_best = state.get("best_confidence")
    if prev_best is None or top > prev_best:
        best_reranked = reranked
        best_confidence = top
    else:
        best_reranked = state.get("best_reranked", reranked)
        best_confidence = prev_best

    return {
        **state,
        "confidence": float(top),
        "confidence_gap": float(gap),
        "best_reranked": best_reranked,
        "best_confidence": float(best_confidence),
    }
