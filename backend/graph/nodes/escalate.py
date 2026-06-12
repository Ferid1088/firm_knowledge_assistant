"""Node: escalate — widen pool, reactive query-rewrite on first escalation."""
from __future__ import annotations

from backend.config import REWRITE, OLLAMA_MODEL, DEFAULT_ANSWER_LANG
from backend.graph.state import RAGState


def escalate(state: RAGState) -> RAGState:
    from backend.graph.nodes.prepare_query import _decompose_question
    from backend.tools.rewriter import rewrite_query

    attempts = state.get("attempts", 0) + 1
    sub_questions = state.get("sub_questions", [state["question"]])
    if len(sub_questions) == 1:
        query_lang = state.get("query_lang", DEFAULT_ANSWER_LANG)
        decomposed = _decompose_question(state["question"], query_lang)
        if decomposed and decomposed != sub_questions:
            sub_questions = decomposed

    result = {
        **state,
        "attempts": attempts,
        "sub_questions": sub_questions,
        "candidate_pool": [],
        "reranked": [],
        "escalation_reason": (
            f"confidence={state.get('confidence', 0):.2f}, "
            f"gap={state.get('confidence_gap', 0):.2f}, attempt {attempts}"
        ),
    }

    if (
        REWRITE.get("enabled")
        and REWRITE.get("trigger") == "reactive"
        and "rewritten_query" not in state
    ):
        query_lang = state.get("query_lang", DEFAULT_ANSWER_LANG)
        rewritten = rewrite_query(state["question"], query_lang, REWRITE, OLLAMA_MODEL)
        result["rewritten_query"] = rewritten or ""

    return result
