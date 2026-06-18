"""Node: score_confidence — top-1 score and gap-to-tail for the router."""
from __future__ import annotations

from backend.graph.state import RAGState


def score_confidence(state: RAGState) -> RAGState:
    """Compute top-1 reranker score and gap-to-tail for the router's confidence gate."""
    reranked = state.get("reranked", [])
    if not reranked:
        return {**state, "confidence": 0.0, "confidence_gap": 0.0}

    scores = [h.get("rerank_score", h.get("score", 0.0)) for h in reranked]
    top = scores[0]
    gap = top - scores[1] if len(scores) > 1 else top
    return {**state, "confidence": float(top), "confidence_gap": float(gap)}
