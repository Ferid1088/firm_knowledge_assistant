"""Node: prepare_query — language detection, answer-lang resolution, query
translation (cached), multi-part decomposition, and date range extraction."""
from __future__ import annotations

import re

from backend.config import ENABLE_TRANSLATED_BM25
from backend.services.language import registry
from backend.graph.retrieval.state import RAGState
from backend.graph.retrieval.utils import (
    detect_lang, parse_explicit_lang, translate_query,
    is_multi_part, decompose_question,
)
from backend.tools.dates import extract_and_normalize


def prepare_query(state: RAGState) -> RAGState:
    """Detect language, resolve answer_lang, cache translations, decompose multi-part queries."""
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

    # Date range extraction — detect dates and temporal keywords (DE + EN)
    date_from = state.get("date_filter_from")
    date_to = state.get("date_filter_to")

    if date_from is None and date_to is None:
        query_dates = extract_and_normalize(question)
        if query_dates:
            q_lower = question.lower()

            has_before = bool(re.search(
                r"\b(vor|before|bis zum|bis|until|spätestens)\b", q_lower))
            has_after = bool(re.search(
                r"\b(nach|after|seit|since|ab|from|frühestens)\b", q_lower))
            has_between = bool(re.search(
                r"\b(zwischen|between)\b", q_lower))

            if has_between and len(query_dates) >= 2:
                date_from = min(query_dates)
                date_to = max(query_dates)
            elif has_before:
                date_to = max(query_dates)
            elif has_after:
                date_from = min(query_dates)
            else:
                # No temporal keyword — use dates as both bounds (exact match range)
                date_from = min(query_dates)
                date_to = max(query_dates)

    return {
        **state,
        "query_lang": query_lang,
        "answer_lang": answer_lang,
        "translated_queries": translated,
        "sub_questions": sub_questions,
        "attempts": state.get("attempts", 0),
        "date_filter_from": date_from,
        "date_filter_to": date_to,
    }
