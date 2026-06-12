"""Node: answer — LLM generation + robust claim verification."""
from __future__ import annotations
import json
import re

from backend.config import OLLAMA_MODEL, OLLAMA_TEMPERATURE, DEFAULT_ANSWER_LANG
from backend.graph.state import RAGState
from backend.graph.utils import load_prompt
from backend.services.tracing import observe_if_enabled
from backend.adapters import llm as llm_adapter


def _normalize_string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_for_match(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return re.sub(r"[^\w]+", "", lowered)


def _verify_claims(claims: list[dict], hits: list[dict]) -> list[dict]:
    for c in claims:
        idx = c.get("source", 1) - 1
        if 0 <= idx < len(hits):
            src_text = hits[idx].get("text", "")
            context_text = hits[idx].get("context_text", "")
            quote = c.get("quote", "")
            nq = _normalize_for_match(quote)
            ns = _normalize_for_match(src_text)
            nc = _normalize_for_match(context_text)
            c["verified"] = bool(nq) and (nq in ns or nq in nc)
        else:
            c["verified"] = False
    return claims


@observe_if_enabled(name="ollama.answer", as_type="generation", capture_output=False)
def answer(state: RAGState) -> RAGState:
    from backend.graph.nodes.abstain import abstain

    reranked = state.get("reranked", [])
    if not reranked:
        return abstain(state)

    answer_lang = state.get("answer_lang", DEFAULT_ANSWER_LANG)
    question = state["question"]

    template = load_prompt("answer", answer_lang)
    sources_text = "\n\n".join(f"[{i+1}] {h['context_text']}" for i, h in enumerate(reranked))
    prompt = template.format(sources=sources_text, question=question)

    raw = llm_adapter.chat(prompt, temperature=OLLAMA_TEMPERATURE)

    # Strip think blocks and markdown fences
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
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
        return {**state, "answer": raw, "supporting_points": [], "caveats": [],
                "claims": [], "artifact_chunks": []}
    except Exception as e:
        return {**state, "answer": f"Error generating answer: {e}",
                "supporting_points": [], "caveats": [], "claims": [], "artifact_chunks": []}
