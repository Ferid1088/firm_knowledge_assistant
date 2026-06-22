"""Node: escalate — bump attempt count, widen pool + reranker window, clear pool to retry.

D1: progressive pool widening + reranker max_length doubling (capped).
D2: reranker_cache is PRESERVED across escalation loops (not cleared).
"""
from __future__ import annotations

from backend.config import (
    RERANKER_MAX_LENGTH,
    RERANKER_MAX_LENGTH_CAP,
    RETRIEVE_DEEP_POOL,
    RETRIEVE_DEEP_POOL_CAP,
)
from backend.graph.retrieval.state import RAGState


def escalate(state: RAGState) -> RAGState:
    """Increment attempts, double pool size + reranker window (capped), clear pool for retry."""
    attempts = state.get("attempts", 0) + 1

    # D1: double retrieve pool size, capped
    current_pool_size = state.get("retrieve_pool_size") or RETRIEVE_DEEP_POOL
    new_pool_size = min(current_pool_size * 2, RETRIEVE_DEEP_POOL_CAP)

    # D1: double reranker max_length, capped
    current_max_length = state.get("reranker_max_length") or RERANKER_MAX_LENGTH
    new_max_length = min(current_max_length * 2, RERANKER_MAX_LENGTH_CAP)

    return {
        **state,
        "attempts": attempts,
        "candidate_pool": [],
        "reranked": [],
        "retrieve_pool_size": new_pool_size,
        "reranker_max_length": new_max_length,
        # D2: reranker_cache intentionally NOT cleared — scores persist across loops
        "escalation_reason": (
            f"confidence={state.get('confidence', 0):.2f} < threshold, attempt {attempts}; "
            f"pool_size={new_pool_size}, max_length={new_max_length}"
        ),
    }
