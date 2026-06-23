"""Node: answer — local LLM in answer_lang, JSON contract, quote-verification,
and artifact_chunks population for the UI."""
from __future__ import annotations
import json
import re

from backend.config import OLLAMA_MODEL, OLLAMA_TEMPERATURE, DEFAULT_ANSWER_LANG
from backend.graph.retrieval.state import RAGState
from backend.graph.retrieval.utils import load_prompt, verify_claims
from backend.graph.retrieval.nodes.abstain import abstain

_HISTORY_LABEL = {"de": "Bisheriger Verlauf", "en": "Conversation history"}


def _format_history(history: list[dict], lang: str) -> str:
    """Render prior conversation turns as a labeled block, or "" if empty.

    Kept out of the prompt's JSON-contract structure (CLAUDE.md: prompt
    structure must stay stable) — this is plain context, prepended before
    "Quellen:"/"Sources:".
    """
    if not history:
        return ""
    label = _HISTORY_LABEL.get(lang, _HISTORY_LABEL["en"])
    lines = [f"{m['role']}: {m['text']}" for m in history]
    return f"{label}:\n" + "\n".join(lines) + "\n\n"


def answer(state: RAGState) -> RAGState:
    """Call local LLM, verify citations against source chunks, populate artifact_chunks."""
    import ollama

    # Prefer expanded_context (parent heading prepended) over raw reranked hits.
    # expanded_context is produced by the expand_context node; if absent, fall back
    # to reranked.  Citations still resolve against reranked (the precise children).
    expanded = state.get("expanded_context")
    reranked = state.get("reranked", [])
    context_hits = expanded if expanded else reranked
    if not context_hits:
        return abstain(state)

    answer_lang = state.get("answer_lang", DEFAULT_ANSWER_LANG)
    question = state["question"]

    template = load_prompt("answer", answer_lang)
    sources_text = "\n\n".join(
        f"[{i+1}] {h.get('expanded_text', h.get('context_text', h['text']))}"
        for i, h in enumerate(context_hits)
    )
    history_text = _format_history(state.get("history", []), answer_lang)
    prompt = template.format(sources=sources_text, question=question, history=history_text)

    try:
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": OLLAMA_TEMPERATURE},
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
        claims = verify_claims(data.get("claims", []), context_hits)

        # Build artifact_chunks (UI only; NEVER put into model prompt)
        artifact_chunks = []
        for c in claims:
            if not c.get("verified"):
                continue
            idx = c.get("source", 1) - 1
            if 0 <= idx < len(context_hits):
                h = context_hits[idx]
                artifact_chunks.append({
                    "source": c["source"],
                    "chunk_id": h.get("chunk_id", ""),
                    "text": h["text"],
                    "address": h["address"],
                    "quote": c["quote"],
                    "version_id": h.get("version_id", ""),
                    "version_num": h.get("version_num", 1),
                    "ingest_time": h.get("ingest_time", ""),
                })

        return {
            **state,
            "answer": data.get("answer", ""),
            "claims": claims,
            "artifact_chunks": artifact_chunks,
        }

    except json.JSONDecodeError:
        # LLM didn't return valid JSON — use raw text as answer without citations
        return {**state, "answer": raw, "claims": [], "artifact_chunks": []}
    except Exception as e:
        return {**state, "answer": f"Error generating answer: {e}", "claims": [], "artifact_chunks": []}
