"""Shared helpers and lazy-loaded singletons for the LangGraph RAG nodes."""
from __future__ import annotations
import json
import re
from pathlib import Path

from backend.config import (
    OLLAMA_MODEL, RERANKER_MODEL_ID, DEFAULT_ANSWER_LANG, QDRANT_DIR,
    LANG_DETECTION_CONFIDENCE, RERANKER_DEVICE,
    ENABLE_QUERY_REWRITE, QUERY_REWRITE_MIN_LENGTH,
    ENABLE_LLM_DECOMPOSITION, DECOMPOSE_MAX_SUBQUESTIONS,
    ENABLE_HYDE,
)
from backend.services.language import registry


# -- Lazy-loaded singletons ------------------------------------------------

_embedder = None
_reranker = None
_collection_tuple = None
_bm25_indices: dict = {}


def get_embedder():
    """Lazy-load and cache the Qwen3 embedder singleton."""
    global _embedder
    if _embedder is None:
        from backend.adapters.embedder import load_embedder
        _embedder = load_embedder()
    return _embedder


def get_reranker():
    """Lazy-load and cache the Qwen3-Reranker singleton."""
    global _reranker
    if _reranker is None:
        from backend.adapters.reranker import Qwen3Reranker
        _reranker = Qwen3Reranker(RERANKER_MODEL_ID, device=RERANKER_DEVICE)
    return _reranker


def get_collection():
    """Lazy-load and cache the (QdrantClient, collection_name) tuple."""
    global _collection_tuple
    if _collection_tuple is None:
        from backend.services.store import get_collection as _get_collection
        _collection_tuple = _get_collection(QDRANT_DIR)
    return _collection_tuple


def get_bm25_indices() -> dict:
    """Return the process-wide BM25 index map {lang_code: BM25Index}."""
    return _bm25_indices


def set_bm25_indices(indices: dict):
    """Called by the ingest pipeline after indexing to make BM25 available at query time."""
    global _bm25_indices
    _bm25_indices = indices


# -- Prompt loader ---------------------------------------------------------

def load_prompt(purpose: str, lang: str) -> str:
    """Load a prompt template by (purpose, lang), falling back to German if missing."""
    ld = registry.get(lang)
    p = Path("prompts") / f"{purpose}_{ld.prompt_key}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")
    # Fallback to German
    fallback = Path("prompts") / f"{purpose}_de.txt"
    return fallback.read_text(encoding="utf-8") if fallback.exists() else ""


# -- Language detection + query translation --------------------------------

def detect_lang(text: str) -> str:
    """Detect language code of text; returns German default for unknowns or errors.

    Uses detect_langs() (with probabilities) instead of detect() so that
    short text with low confidence stays as German rather than misfiring.
    A non-German language is accepted only if its probability exceeds 0.80;
    otherwise we fall back to the German default (house language).
    """
    try:
        from langdetect import detect_langs, DetectorFactory
        DetectorFactory.seed = 0  # deterministic results
        known = {ld.code for ld in registry.all()}
        results = detect_langs(text)  # e.g. [de:0.857, en:0.142]
        # Best candidate
        best = results[0]
        lang = best.lang
        prob = best.prob
        if lang not in known:
            return DEFAULT_ANSWER_LANG
        # For any non-default language (i.e. not German) require high confidence
        # to avoid misfiring on short German text with English-looking words.
        if lang != DEFAULT_ANSWER_LANG and prob < LANG_DETECTION_CONFIDENCE:
            return DEFAULT_ANSWER_LANG
        return lang
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


# -- E1: Query rewriting (vague / conversational / typo) -------------------

# Anaphoric terms that signal a conversational follow-up needing coreference resolution
_ANAPHORIC_DE = {"diese", "dieser", "dieses", "das", "davon", "dabei", "dazu", "dem", "deren", "dessen"}
_ANAPHORIC_EN = {"it", "this", "that", "these", "those", "its", "them"}
_ANAPHORIC_ALL = _ANAPHORIC_DE | _ANAPHORIC_EN


def _has_anaphoric_reference(question: str) -> bool:
    """Return True if the query contains anaphoric terms needing coreference resolution."""
    words = set(re.findall(r"\b\w+\b", question.lower()))
    return bool(words & _ANAPHORIC_ALL)


def _is_vague_query(question: str) -> bool:
    """Return True if the query is short and lacks specific identifiers."""
    words = question.split()
    if len(words) >= 5:
        return False
    # Has digit, section symbol, or uppercase proper noun > 3 chars -> specific enough
    if re.search(r"\d", question):
        return False
    if "§" in question:
        return False
    if any(w[0].isupper() and len(w) > 3 and w != words[0] for w in words if w):
        return False
    return True


def _is_keyword_fragment(question: str) -> bool:
    """Return True if query looks like keyword fragments (no verb-like structure)."""
    words = question.split()
    if len(words) > 6:
        return False
    # No question mark and no verb-like endings -> likely fragments
    if "?" in question:
        return False
    # Very short keyword-only input
    return len(words) <= 3 and not any(w.lower().endswith(("en", "st", "et", "ed", "ing", "ung"))
                                       for w in words)


def rewrite_query(question: str, history: list[dict] | None, lang: str) -> str | None:
    """Rewrite a vague/conversational/fragment query using local Ollama LLM.

    Returns the rewritten query string, or None if the original is already
    specific enough (caller should keep the original).
    """
    if not ENABLE_QUERY_REWRITE:
        return None
    if len(question.split()) < QUERY_REWRITE_MIN_LENGTH and not _is_keyword_fragment(question):
        return None

    try:
        import ollama
    except ImportError:
        return None

    # 1. Conversational follow-up: resolve anaphoric references using history
    if history and _has_anaphoric_reference(question):
        last_answer = ""
        for turn in reversed(history):
            if turn.get("role") == "assistant":
                last_answer = turn.get("text", turn.get("content", ""))
                break
        if last_answer:
            prompt = (
                f"/no_think\nThe user's follow-up query contains a pronoun or demonstrative "
                f"that refers to something in the previous answer. Rewrite the query to be "
                f"self-contained by resolving the reference.\n\n"
                f"Previous answer (excerpt): {last_answer[:500]}\n"
                f"Follow-up query: {question}\n\n"
                f"Return ONLY the rewritten query, nothing else."
            )
            try:
                resp = ollama.chat(
                    model=OLLAMA_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0},
                )
                rewritten = resp["message"]["content"].strip()
                if rewritten and rewritten != question:
                    return rewritten
            except Exception:
                pass

    # 2. Vague query: make it more specific
    if _is_vague_query(question):
        prompt = (
            f"/no_think\nThe following query is vague and underspecified. "
            f"Rewrite it as a more specific question that a document retrieval system "
            f"can answer. Keep the same intent; add specificity.\n\n"
            f"Query: {question}\n\n"
            f"Return ONLY the rewritten query, nothing else."
        )
        try:
            resp = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0},
            )
            rewritten = resp["message"]["content"].strip()
            if rewritten and rewritten != question:
                return rewritten
        except Exception:
            pass

    # 3. Keyword fragment: form a complete question
    if _is_keyword_fragment(question):
        prompt = (
            f"/no_think\nThe following input is a keyword fragment, not a complete question. "
            f"Turn it into a well-formed question that a document search system can answer.\n\n"
            f"Input: {question}\n\n"
            f"Return ONLY the rewritten question, nothing else."
        )
        try:
            resp = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0},
            )
            rewritten = resp["message"]["content"].strip()
            if rewritten and rewritten != question:
                return rewritten
        except Exception:
            pass

    return None


# -- Multi-part detection + decomposition -----------------------------------

def is_multi_part(question: str) -> bool:
    """Check for multi-part questions: fast keyword heuristic + optional LLM fallback."""
    indicators = [" und ", " and ", " sowie ", " compare ", " vergleich", " both "]
    q_lower = question.lower()
    keyword_hit = any(ind in q_lower for ind in indicators) or question.count("?") > 1

    if keyword_hit and ENABLE_LLM_DECOMPOSITION:
        # LLM confirmation: keywords like "und" appear in non-multi-part queries too
        try:
            import ollama
            prompt = (
                f"/no_think\nDoes the following query ask multiple INDEPENDENT questions "
                f"that should each be answered separately? Answer ONLY 'yes' or 'no'.\n\n"
                f"Query: {question}"
            )
            resp = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0},
            )
            answer = resp["message"]["content"].strip().lower()
            return answer.startswith("yes")
        except Exception:
            return keyword_hit  # fallback to keyword result on LLM failure

    return keyword_hit


def _validate_sub_questions(subs: list[str], original: str) -> list[str]:
    """Filter out sub-questions that reference each other (not truly independent)."""
    # Cross-reference indicators: if sub_i mentions text unique to sub_j, they depend
    cross_ref_patterns = [
        r"\b(the above|the previous|the first|see above|obige|vorige|erste)\b",
        r"\b(based on that|building on|aufbauend)\b",
    ]
    valid = []
    for sq in subs:
        is_cross_ref = any(re.search(pat, sq.lower()) for pat in cross_ref_patterns)
        if not is_cross_ref and sq.strip():
            valid.append(sq.strip())
    return valid if valid else [original]


def decompose_question(question: str, lang: str) -> list[str]:
    """Use local LLM to decompose a multi-part question into sub-questions.

    E2: Validates independence and caps at DECOMPOSE_MAX_SUBQUESTIONS.
    """
    try:
        import ollama
        max_q = DECOMPOSE_MAX_SUBQUESTIONS
        if lang == "de":
            prompt = (
                f"/no_think\nZerlege die folgende Frage in 2-{max_q} eigenständige Teilfragen. "
                f"Jede Teilfrage muss unabhängig von den anderen verständlich sein. "
                f"Gib NUR eine JSON-Liste von Strings zurück, z.B. [\"Frage 1\", \"Frage 2\"].\n\n"
                f"Frage: {question}"
            )
        else:
            prompt = (
                f"/no_think\nDecompose the following question into 2-{max_q} independent sub-questions. "
                f"Each sub-question must be self-contained and understandable on its own. "
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
            subs = json.loads(match.group())
            # Cap and validate independence
            subs = subs[:max_q]
            return _validate_sub_questions(subs, question)
    except Exception:
        pass
    return [question]


# -- E3: HyDE — Hypothetical Document Embedding ---------------------------

def generate_hyde_passage(question: str, lang: str) -> str | None:
    """Generate a hypothetical answer passage (~100 words) for HyDE retrieval.

    Returns the passage text, or None if generation fails or HyDE is disabled.
    Used by prepare_query to populate state['hyde_passage']; the retrieve node
    embeds this for a second dense pass and merges via RRF.
    """
    if not ENABLE_HYDE:
        return None
    try:
        import ollama
        if lang == "de":
            prompt = (
                f"/no_think\nSchreibe einen hypothetischen Absatz (~100 Wörter), der die "
                f"folgende Frage direkt beantwortet. Schreibe im Stil eines technischen "
                f"Dokuments. Gib NUR den Absatz zurück, keine Einleitung.\n\n"
                f"Frage: {question}"
            )
        else:
            prompt = (
                f"/no_think\nWrite a hypothetical passage (~100 words) that directly answers "
                f"the following question. Write in the style of a technical document. "
                f"Return ONLY the passage, no preamble.\n\n"
                f"Question: {question}"
            )
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3},  # slight creativity for hypothetical generation
        )
        passage = resp["message"]["content"].strip()
        return passage if passage else None
    except Exception:
        return None


# -- Claim verification (shared by answer node) ---------------------------

def verify_claims(claims: list[dict], hits: list[dict]) -> list[dict]:
    """Check each claim's quote against its cited source chunk (whitespace-normalised)."""
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
