"""Node: escalate — bump attempt count and clear the pool to retry retrieval."""
from __future__ import annotations

from backend.graph.state import RAGState


def escalate(state: RAGState) -> RAGState:
    attempts = state.get("attempts", 0) + 1
    # Simple escalation: widen pool size will happen automatically on next retrieve
    # (the retrieve node always uses RETRIEVE_DEEP_POOL; on escalation we could
    # increase it — here we just increment attempts and clear the pool)
    return {
        **state,
        "attempts": attempts,
        "candidate_pool": [],
        "reranked": [],
        "escalation_reason": f"confidence={state.get('confidence', 0):.2f} < threshold, attempt {attempts}",
    }
