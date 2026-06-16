"""Shared helpers and lazy-loaded singletons for the LangGraph RAG nodes."""
from __future__ import annotations
import json
import re
from pathlib import Path

from backend.config import OLLAMA_MODEL, RERANKER_MODEL_ID, DEFAULT_ANSWER_LANG, QDRANT_DIR
from backend.services.language import registry


# ── Lazy-loaded singletons ─────────────────────────────────────────────────

_embedder = None
_reranker = None
_collection_tuple = None
_bm25_indices: dict = {}


def get_embedder():
    global _embedder
    if _embedder is None:
        from backend.adapters.embedder import load_embedder
        _embedder = load_embedder()
    return _embedder


def get_reranker():
    global _reranker
    if _reranker is None:
        from backend.adapters.reranker import Qwen3Reranker
        _reranker = Qwen3Reranker(RERANKER_MODEL_ID, device="cpu")
    return _reranker


def get_collection():
    global _collection_tuple
    if _collection_tuple is None:
        from backend.services.store import get_collection as _get_collection
        _collection_tuple = _get_collection(QDRANT_DIR)
    return _collection_tuple


def get_bm25_indices() -> dict:
    return _bm25_indices


def set_bm25_indices(indices: dict):
    """Called by the ingest pipeline after indexing to make BM25 available at query time."""
    global _bm25_indices
    _bm25_indices = indices


# ── Prompt loader ──────────────────────────────────────────────────────────

def load_prompt(purpose: str, lang: str) -> str:
    ld = registry.get(lang)
    p = Path("prompts") / f"{purpose}_{ld.prompt_key}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")
    # Fallback to German
    fallback = Path("prompts") / f"{purpose}_de.txt"
    return fallback.read_text(encoding="utf-8") if fallback.exists() else ""


# ── Language detection + query translation ─────────────────────────────────

def detect_lang(text: str) -> str:
    try:
        from langdetect import detect, DetectorFactory
        DetectorFactory.seed = 0  # deterministic results
        lang = detect(text)
        known = {ld.code for ld in registry.all()}
        return lang if lang in known else DEFAULT_ANSWER_LANG
    except Exception:
        return DEFAULT_ANSWER_LANG


def parse_explicit_lang(question: str) -> str | None:
    """Look for explicit language instructions like 'answer in English'."""
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


def translate_query(query: str, target_lang: str, source_lang: str) -> str:
    """Translate query using local Ollama LLM. Never a cloud API."""
    if source_lang == target_lang:
        return query
    try:
        import ollama
        prompt = (
            f"/no_think\nTranslate the following query from {source_lang} to {target_lang}. "
            f"Translate ONLY natural language — do NOT translate codes, numbers, or technical identifiers. "
            f"Return ONLY the translated text, nothing else.\n\nQuery: {query}"
        )
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0},
        )
        return resp["message"]["content"].strip()
    except Exception:
        return query  # fallback: use original


def is_multi_part(question: str) -> bool:
    indicators = [" und ", " and ", " sowie ", " compare ", " vergleich", " both "]
    q_lower = question.lower()
    return any(ind in q_lower for ind in indicators) or question.count("?") > 1


def decompose_question(question: str, lang: str) -> list[str]:
    """Use local LLM to decompose a multi-part question into sub-questions."""
    try:
        import ollama
        if lang == "de":
            prompt = (
                f"/no_think\nZerlege die folgende Frage in 2-4 eigenständige Teilfragen. "
                f"Gib NUR eine JSON-Liste von Strings zurück, z.B. [\"Frage 1\", \"Frage 2\"].\n\n"
                f"Frage: {question}"
            )
        else:
            prompt = (
                f"/no_think\nDecompose the following question into 2-4 independent sub-questions. "
                f"Return ONLY a JSON array of strings, e.g. [\"Q1\", \"Q2\"].\n\n"
                f"Question: {question}"
            )
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0},
        )
        raw = resp["message"]["content"].strip()
        # Extract JSON array
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return [question]


# ── Claim verification (shared by answer node) ──────────────────────────────

def verify_claims(claims: list[dict], hits: list[dict]) -> list[dict]:
    for c in claims:
        idx = c.get("source", 1) - 1
        if 0 <= idx < len(hits):
            src_text = hits[idx]["text"]
            quote = c.get("quote", "")
            # Normalize whitespace + case for verification
            c["verified"] = (
                re.sub(r"\s+", "", quote.lower()) in re.sub(r"\s+", "", src_text.lower())
            )
        else:
            c["verified"] = False
    return claims
