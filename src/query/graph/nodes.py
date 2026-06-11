"""LangGraph nodes for the RAG pipeline.

Node order: prepare_query -> retrieve -> rerank -> score_confidence
  -> answer  (confidence OK)
  -> escalate -> retrieve  (low confidence, attempts < max)
  -> abstain  (attempts exhausted)
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any

from config import (
    OLLAMA_MODEL, OLLAMA_TEMPERATURE, RETRIEVE_K, RETRIEVE_DEEP_POOL,
    MAX_ATTEMPTS, CONFIDENCE_THRESHOLD, CONFIDENCE_GAP_MIN,
    ENABLE_TRANSLATED_BM25, RERANKER_MODEL_ID, RERANKER_TOP_K, DEFAULT_ANSWER_LANG,
    QDRANT_DIR,
)
from src.common.tracing import observe_if_enabled
from src.common.language import registry
from src.query.graph.state import RAGState


# ── Lazy-loaded singletons ─────────────────────────────────────────────────

_embedder = None
_reranker = None
_collection_tuple = None
_bm25_indices: dict = {}


def _get_embedder():
    global _embedder
    if _embedder is None:
        from src.common.embed import load_embedder
        _embedder = load_embedder()
    return _embedder


def _get_reranker():
    global _reranker
    if _reranker is None:
        from src.query.reranker import Qwen3Reranker
        # MPS currently produces NaN scores for this model (Qwen3Reranker falls
        # back to CPU on NaN/OOM anyway, but starting on CPU avoids a wasted
        # first-batch round trip on every process start).
        _reranker = Qwen3Reranker(RERANKER_MODEL_ID, device="cpu")
    return _reranker


def _get_collection():
    global _collection_tuple
    if _collection_tuple is None:
        from src.common.store import get_collection
        _collection_tuple = get_collection(QDRANT_DIR)
    return _collection_tuple


def set_bm25_indices(indices: dict):
    """Called by pipeline after indexing to make BM25 available at query time."""
    global _bm25_indices
    _bm25_indices = indices


# ── Prompt loader ──────────────────────────────────────────────────────────

def _load_prompt(purpose: str, lang: str) -> str:
    ld = registry.get(lang)
    p = Path("prompts") / f"{purpose}_{ld.prompt_key}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")
    # Fallback to German
    fallback = Path("prompts") / f"{purpose}_de.txt"
    return fallback.read_text(encoding="utf-8") if fallback.exists() else ""


# ── Language detection + query translation ─────────────────────────────────

def _detect_lang(text: str) -> str:
    try:
        from langdetect import detect
        lang = detect(text)
        known = {ld.code for ld in registry.all()}
        return lang if lang in known else DEFAULT_ANSWER_LANG
    except Exception:
        return DEFAULT_ANSWER_LANG


def _retrieve_pool_size(attempts: int) -> int:
    expansion = max(10, RETRIEVE_DEEP_POOL // 2)
    return RETRIEVE_DEEP_POOL + (attempts * expansion)


def _answer_source_limit(attempts: int) -> int:
    return max(RETRIEVE_K, RERANKER_TOP_K + (attempts * 2))


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _normalize_for_match(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return re.sub(r"[^\w]+", "", lowered)


def _parse_explicit_lang(question: str) -> str | None:
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


@observe_if_enabled(name="ollama.translate_query", as_type="generation")
def _translate_query(query: str, target_lang: str, source_lang: str) -> str:
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
            think=False,
        )
        return resp["message"]["content"].strip()
    except Exception:
        return query  # fallback: use original


def _is_multi_part(question: str) -> bool:
    indicators = [" und ", " and ", " sowie ", " compare ", " vergleich", " both "]
    q_lower = question.lower()
    return any(ind in q_lower for ind in indicators) or question.count("?") > 1


@observe_if_enabled(name="ollama.decompose_question", as_type="generation")
def _decompose_question(question: str, lang: str) -> list[str]:
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
            think=False,
        )
        raw = resp["message"]["content"].strip()
        # Extract JSON array
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return [question]


# ── Node: prepare_query ────────────────────────────────────────────────────

def prepare_query(state: RAGState) -> RAGState:
    question = state["question"]
    active_codes = state.get("active_lang_codes", ["de"])

    query_lang = _detect_lang(question)
    explicit_lang = _parse_explicit_lang(question)
    answer_lang = registry.resolve_answer_lang(query_lang, explicit_lang)

    # Translate ONCE into each active language (cached in state)
    translated = state.get("translated_queries") or {}
    if not translated:
        for code in active_codes:
            if code == query_lang:
                translated[code] = question
            elif ENABLE_TRANSLATED_BM25:
                translated[code] = _translate_query(question, code, query_lang)
            else:
                translated[code] = question

    # Multi-part detection
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


# ── Node: retrieve ─────────────────────────────────────────────────────────

def retrieve(state: RAGState) -> RAGState:
    from src.common.store import search as store_search

    sub_questions = state.get("sub_questions", [state["question"]])
    active_codes = state.get("active_lang_codes", ["de"])
    translated = state.get("translated_queries", {})
    attempts = state.get("attempts", 0)
    k = _retrieve_pool_size(attempts)

    all_hits: list[dict] = []
    seen_ids: set[str] = set()

    for sub_q in sub_questions:
        # Dense pass uses the original query (cross-lingual model handles it)
        hits = store_search(
            _get_collection(),
            _get_embedder(),
            sub_q,
            _bm25_indices,
            active_codes,
            k=k,
        )
        for h in hits:
            cid = h["chunk_id"]
            if cid not in seen_ids:
                seen_ids.add(cid)
                all_hits.append(h)

    # For translated BM25 passes, run a second pass per language with the translated query
    if ENABLE_TRANSLATED_BM25:
        for lang_code, trans_q in translated.items():
            if trans_q == sub_questions[0]:
                continue  # already covered
            hits = store_search(
                _get_collection(),
                _get_embedder(),
                trans_q,
                _bm25_indices,
                [lang_code],
                k=k // 2,
            )
            for h in hits:
                cid = h["chunk_id"]
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    all_hits.append(h)

    # Sort by score, keep deep pool
    all_hits.sort(key=lambda x: x["score"], reverse=True)
    return {**state, "candidate_pool": all_hits[:k], "effective_retrieve_k": k}


# ── Node: rerank ───────────────────────────────────────────────────────────

def rerank(state: RAGState) -> RAGState:
    pool = state.get("candidate_pool", [])
    if not pool:
        return {**state, "reranked": []}

    question = state["question"]
    reranker = _get_reranker()
    answer_k = min(len(pool), _answer_source_limit(state.get("attempts", 0)))

    pairs = [(question, h["context_text"]) for h in pool]
    try:
        scores = reranker.predict(pairs)
        ranked = sorted(zip(pool, scores), key=lambda x: x[1], reverse=True)
        reranked = []
        for hit, score in ranked[:answer_k]:
            reranked.append({**hit, "rerank_score": float(score)})
    except Exception:
        # If reranker fails (e.g. not yet downloaded), fall back to retrieval order
        reranked = pool[:answer_k]

    return {**state, "reranked": reranked}


# ── Node: score_confidence ─────────────────────────────────────────────────

def score_confidence(state: RAGState) -> RAGState:
    reranked = state.get("reranked", [])
    if not reranked:
        return {**state, "confidence": 0.0, "confidence_gap": 0.0}

    scores = [h.get("rerank_score", h.get("score", 0.0)) for h in reranked]
    top = scores[0]
    gap = top - scores[1] if len(scores) > 1 else top
    return {**state, "confidence": float(top), "confidence_gap": float(gap)}


# ── Node: escalate ─────────────────────────────────────────────────────────

def escalate(state: RAGState) -> RAGState:
    attempts = state.get("attempts", 0) + 1
    sub_questions = state.get("sub_questions", [state["question"]])
    if len(sub_questions) == 1:
        query_lang = state.get("query_lang", DEFAULT_ANSWER_LANG)
        decomposed = _decompose_question(state["question"], query_lang)
        if decomposed and decomposed != sub_questions:
            sub_questions = decomposed

    return {
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


# ── Node: answer ───────────────────────────────────────────────────────────

def _verify_claims(claims: list[dict], hits: list[dict]) -> list[dict]:
    for c in claims:
        idx = c.get("source", 1) - 1
        if 0 <= idx < len(hits):
            src_text = hits[idx].get("text", "")
            context_text = hits[idx].get("context_text", "")
            quote = c.get("quote", "")
            normalized_quote = _normalize_for_match(quote)
            normalized_src = _normalize_for_match(src_text)
            normalized_context = _normalize_for_match(context_text)
            c["verified"] = bool(normalized_quote) and (
                normalized_quote in normalized_src or normalized_quote in normalized_context
            )
        else:
            c["verified"] = False
    return claims


@observe_if_enabled(name="ollama.answer", as_type="generation", capture_output=False)
def answer(state: RAGState) -> RAGState:
    import ollama

    reranked = state.get("reranked", [])
    if not reranked:
        return abstain(state)

    answer_lang = state.get("answer_lang", DEFAULT_ANSWER_LANG)
    question = state["question"]

    template = _load_prompt("answer", answer_lang)
    sources_text = "\n\n".join(f"[{i+1}] {h['context_text']}" for i, h in enumerate(reranked))
    prompt = template.format(sources=sources_text, question=question)

    try:
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": OLLAMA_TEMPERATURE},
            think=False,
        )
        raw = resp["message"]["content"].strip()
        # Strip <think>...</think> blocks some models still emit
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        # Strip markdown fences if model added them
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Model wrapped JSON in prose — extract the outermost {...} block
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise
            data = json.loads(match.group())
        claims = _verify_claims(data.get("claims", []), reranked)
        supporting_points = _normalize_string_list(data.get("supporting_points", []))
        caveats = _normalize_string_list(data.get("caveats", []))
        if not supporting_points:
            supporting_points = [
                c.get("text", "").strip()
                for c in claims
                if c.get("verified") and c.get("text", "").strip()
            ][:3]

        answer_text = str(data.get("answer", "")).strip()
        if not answer_text and supporting_points:
            answer_text = supporting_points[0]

        # Build artifact_chunks (UI only; NEVER put into model prompt)
        artifact_chunks = []
        for c in claims:
            idx = c.get("source", 1) - 1
            if 0 <= idx < len(reranked):
                h = reranked[idx]
                artifact_chunks.append({
                    "source": c["source"],
                    "chunk_id": h.get("chunk_id", ""),
                    "text": h["text"],
                    "address": h["address"],
                    "quote": c["quote"],
                    "verified": bool(c.get("verified")),
                })

        return {
            **state,
            "answer": answer_text,
            "supporting_points": supporting_points,
            "caveats": caveats,
            "claims": claims,
            "artifact_chunks": artifact_chunks,
        }

    except json.JSONDecodeError:
        # LLM didn't return valid JSON — use raw text as answer without citations
        return {
            **state,
            "answer": raw,
            "supporting_points": [],
            "caveats": [],
            "claims": [],
            "artifact_chunks": [],
        }
    except Exception as e:
        return {
            **state,
            "answer": f"Error generating answer: {e}",
            "supporting_points": [],
            "caveats": [],
            "claims": [],
            "artifact_chunks": [],
        }


# ── Node: abstain ──────────────────────────────────────────────────────────

def abstain(state: RAGState) -> RAGState:
    lang = state.get("answer_lang", DEFAULT_ANSWER_LANG)
    msg = _load_prompt("abstain", lang).strip()
    return {
        **state,
        "answer": msg,
        "supporting_points": [],
        "caveats": [],
        "claims": [],
        "artifact_chunks": [],
    }
