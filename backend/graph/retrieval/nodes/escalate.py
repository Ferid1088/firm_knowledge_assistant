"""Node: escalate — bump attempt count, widen pool + reranker window, clear pool to retry.

D1: progressive pool widening + reranker max_length doubling (capped).
D2: reranker_cache is PRESERVED across escalation loops (not cleared).
HyDE: on attempt >= 2 (after second low-scoring rerank), generate a hypothetical
      answer passage and store it for the next retrieval pass.
"""
from __future__ import annotations

import logging

from backend.config import (
    RERANKER_MAX_LENGTH,
    RERANKER_MAX_LENGTH_CAP,
    RETRIEVE_DEEP_POOL,
    RETRIEVE_DEEP_POOL_CAP,
    ENABLE_HYDE,
)
from backend.graph.retrieval.state import RAGState

log = logging.getLogger("retrieval.escalate")

HYDE_TRIGGER_ATTEMPT = 2  # activate HyDE only after this many failed reranking rounds


def escalate(state: RAGState) -> RAGState:
    """Increment attempts, double pool size + reranker window (capped), clear pool for retry.

    On attempt >= HYDE_TRIGGER_ATTEMPT and ENABLE_HYDE=True, generates a
    hypothetical answer passage so the next retrieval pass can use it for
    a supplementary dense search. HyDE only fires after the second reranking
    loop has already failed — never on the first or second attempt.
    """
    attempts = state.get("attempts", 0) + 1

    # D1: double retrieve pool size, capped
    current_pool_size = state.get("retrieve_pool_size") or RETRIEVE_DEEP_POOL
    new_pool_size = min(current_pool_size * 2, RETRIEVE_DEEP_POOL_CAP)

    # D1: double reranker max_length, capped
    current_max_length = state.get("reranker_max_length") or RERANKER_MAX_LENGTH
    new_max_length = min(current_max_length * 2, RERANKER_MAX_LENGTH_CAP)

    # HyDE: generate hypothetical passage on late escalation
    hyde_passage = state.get("hyde_passage")
    if ENABLE_HYDE and attempts >= HYDE_TRIGGER_ATTEMPT and not hyde_passage:
        try:
            from backend.graph.retrieval.utils import generate_hyde_passage
            query_lang = state.get("query_lang", "de")
            question = state.get("question", "")
            hyde_passage = generate_hyde_passage(question, query_lang)
            if hyde_passage:
                log.info("HyDE activated on attempt %d: generated %d-char passage",
                         attempts, len(hyde_passage))
        except Exception as e:
            log.warning("HyDE generation failed: %s", e)

    return {
        **state,
        "attempts": attempts,
        "candidate_pool": [],
        "reranked": [],
        "retrieve_pool_size": new_pool_size,
        "reranker_max_length": new_max_length,
        "hyde_passage": hyde_passage,
        # D2: reranker_cache intentionally NOT cleared — scores persist across loops
        "escalation_reason": (
            f"confidence={state.get('confidence', 0):.2f} < threshold, attempt {attempts}; "
            f"pool_size={new_pool_size}, max_length={new_max_length}"
            + (", HyDE=active" if hyde_passage else "")
        ),
    }
