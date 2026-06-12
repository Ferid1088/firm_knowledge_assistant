"""Node: prepare_query — language detect, answer_lang, translate, decompose."""
from __future__ import annotations
import json
import re

from backend.config import ENABLE_TRANSLATED_BM25, DEFAULT_ANSWER_LANG
from backend.graph.state import RAGState
from backend.graph.utils import load_prompt
from backend.services.language import registry
from backend.services.tracing import observe_if_enabled
from backend.adapters import llm as llm_adapter


def _detect_lang(text: str) -> str:
    try:
        from langdetect import detect
        lang = detect(text)
        known = {ld.code for ld in registry.all()}
        return lang if lang in known else DEFAULT_ANSWER_LANG
    except Exception:
        return DEFAULT_ANSWER_LANG


def _parse_explicit_lang(question: str) -> str | None:
    patterns = [
        (r"\banswer in english\b", "en"),
        (r"\banswer in german\b", "de"),
        (r"\bauf englisch\b", "en"),
        (r"\bauf deutsch\b", "de"),
        (r"\bin english\b", "en"),
        (r"\bauf deutsch antworten\b", "de"),
    ]
    q_lower = question.lower()
    for pat, lang in patterns:
        if re.search(pat, q_lower):
            return lang
    return None


@observe_if_enabled(name="ollama.translate_query", as_type="generation")
def _translate_query(query: str, target_lang: str, source_lang: str) -> str:
    if source_lang == target_lang:
        return query
    prompt = (
        f"/no_think\nTranslate the following query from {source_lang} to {target_lang}. "
        f"Translate ONLY natural language — do NOT translate codes, numbers, or technical identifiers. "
        f"Return ONLY the translated text, nothing else.\n\nQuery: {query}"
    )
    result = llm_adapter.chat(prompt, temperature=0)
    return result if result else query


def _is_multi_part(question: str) -> bool:
    indicators = [" und ", " and ", " sowie ", " compare ", " vergleich", " both "]
    q_lower = question.lower()
    return any(ind in q_lower for ind in indicators) or question.count("?") > 1


@observe_if_enabled(name="ollama.decompose_question", as_type="generation")
def _decompose_question(question: str, lang: str) -> list[str]:
    if lang == "de":
        prompt = (
            f"/no_think\nZerlege die folgende Frage in 2-4 eigenständige Teilfragen. "
            f"Gib NUR eine JSON-Liste von Strings zurück, z.B. [\"Frage 1\", \"Frage 2\"].\n\nFrage: {question}"
        )
    else:
        prompt = (
            f"/no_think\nDecompose the following question into 2-4 independent sub-questions. "
            f"Return ONLY a JSON array of strings, e.g. [\"Q1\", \"Q2\"].\n\nQuestion: {question}"
        )
    raw = llm_adapter.chat(prompt, temperature=0)
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return [question]


def prepare_query(state: RAGState) -> RAGState:
    question = state["question"]
    active_codes = state.get("active_lang_codes", ["de"])
    query_lang = _detect_lang(question)
    explicit_lang = _parse_explicit_lang(question)
    answer_lang = registry.resolve_answer_lang(query_lang, explicit_lang)

    translated = state.get("translated_queries") or {}
    if not translated:
        for code in active_codes:
            if code == query_lang:
                translated[code] = question
            elif ENABLE_TRANSLATED_BM25:
                translated[code] = _translate_query(question, code, query_lang)
            else:
                translated[code] = question

    sub_questions = state.get("sub_questions")
    if sub_questions is None:
        if _is_multi_part(question):
            sub_questions = _decompose_question(question, query_lang)
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
