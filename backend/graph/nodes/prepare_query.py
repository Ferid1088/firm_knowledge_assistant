"""Node: prepare_query — language detection, answer-lang resolution, query
translation (cached), and multi-part decomposition."""
from __future__ import annotations

from backend.config import ENABLE_TRANSLATED_BM25
from backend.services.language import registry
from backend.graph.state import RAGState
from backend.graph.utils import (
    detect_lang, parse_explicit_lang, translate_query,
    is_multi_part, decompose_question,
)


def prepare_query(state: RAGState) -> RAGState:
    question = state["question"]
    active_codes = state.get("active_lang_codes", ["de"])

    query_lang = detect_lang(question)
    explicit_lang = parse_explicit_lang(question)
    answer_lang = registry.resolve_answer_lang(query_lang, explicit_lang)

    # Translate ONCE into each active language (cached in state)
    translated = state.get("translated_queries") or {}
    if not translated:
        for code in active_codes:
            if code == query_lang:
                translated[code] = question
            elif ENABLE_TRANSLATED_BM25:
                translated[code] = translate_query(question, code, query_lang)
            else:
                translated[code] = question

    # Multi-part detection
    sub_questions = state.get("sub_questions")
    if sub_questions is None:
        if is_multi_part(question):
            sub_questions = decompose_question(question, query_lang)
        else:
            sub_questions = [question]

    return {
        **state,
        "query_lang": query_lang,
        "answer_lang": answer_lang,
        "translated_queries": translated,
        "sub_questions": sub_questions,
        "attempts": state.get("attempts", 0),
    }
