"""Node: abstain — terminal "can't ground this" response in answer_lang."""
from __future__ import annotations

from backend.config import DEFAULT_ANSWER_LANG
from backend.graph.state import RAGState
from backend.graph.utils import load_prompt


def abstain(state: RAGState) -> RAGState:
    """Return the language-keyed abstain message when no grounded answer is possible."""
    lang = state.get("answer_lang", DEFAULT_ANSWER_LANG)
    msg = load_prompt("abstain", lang).strip()
    return {**state, "answer": msg, "claims": [], "artifact_chunks": []}
