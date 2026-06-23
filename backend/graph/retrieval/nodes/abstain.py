"""Node: abstain — terminal "can't ground this" response in answer_lang.

If best_reranked exists from a previous escalation iteration, includes a hint
about the closest match found (without presenting it as a verified answer).
"""
from __future__ import annotations

from backend.config import DEFAULT_ANSWER_LANG
from backend.graph.retrieval.state import RAGState
from backend.graph.retrieval.utils import load_prompt


def abstain(state: RAGState) -> RAGState:
    """Return the language-keyed abstain message when no grounded answer is possible.

    If a previous escalation iteration found results (best_reranked), surface
    the top hit as a "closest match" hint — but clearly marked as unverified.
    """
    lang = state.get("answer_lang", DEFAULT_ANSWER_LANG)
    msg = load_prompt("abstain", lang).strip()

    best = state.get("best_reranked", [])
    best_conf = state.get("best_confidence", 0.0)
    if best and best_conf > 0:
        top_hit = best[0]
        doc_id = top_hit.get("address", {}).get("doc_id", "")
        heading = " > ".join(top_hit.get("address", {}).get("heading_path", []))
        hint_de = f"\n\nNächste Übereinstimmung (nicht verifiziert, Konfidenz {best_conf:.0%}): {doc_id}"
        hint_en = f"\n\nClosest match (unverified, confidence {best_conf:.0%}): {doc_id}"
        if heading:
            hint_de += f" — {heading}"
            hint_en += f" — {heading}"
        msg += hint_de if lang == "de" else hint_en

    return {**state, "answer": msg, "claims": [], "artifact_chunks": []}
