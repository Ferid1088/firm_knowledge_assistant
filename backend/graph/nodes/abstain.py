"""Node: abstain — returns grounded refusal in answer_lang."""
from __future__ import annotations

from backend.config import DEFAULT_ANSWER_LANG
from backend.graph.state import RAGState
from backend.graph.utils import load_prompt


def abstain(state: RAGState) -> RAGState:
    lang = state.get("answer_lang", DEFAULT_ANSWER_LANG)
    msg = load_prompt("abstain", lang).strip()
    return {
        **state,
        "answer": msg,
        "supporting_points": [],
        "caveats": [],
        "claims": [],
        "artifact_chunks": [],
    }
