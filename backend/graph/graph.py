"""Build and compile the LangGraph RAG pipeline."""
from __future__ import annotations
from langgraph.graph import StateGraph, END

from src.query.graph.state import RAGState
from src.query.graph.nodes import (
    prepare_query, retrieve, rerank,
    score_confidence, escalate, answer, abstain,
)
from config import MAX_ATTEMPTS, CONFIDENCE_THRESHOLD, CONFIDENCE_GAP_MIN


def _route_confidence(state: RAGState) -> str:
    conf = state.get("confidence", 0.0)
    attempts = state.get("attempts", 0)
    if conf >= CONFIDENCE_THRESHOLD:
        return "answer"
    if attempts < MAX_ATTEMPTS:
        return "escalate"
    return "abstain"


def build_graph():
    g = StateGraph(RAGState)

    g.add_node("prepare_query", prepare_query)
    g.add_node("retrieve", retrieve)
    g.add_node("rerank", rerank)
    g.add_node("score_confidence", score_confidence)
    g.add_node("escalate", escalate)
    g.add_node("answer", answer)
    g.add_node("abstain", abstain)

    g.set_entry_point("prepare_query")

    g.add_edge("prepare_query", "retrieve")
    g.add_edge("retrieve", "rerank")
    g.add_edge("rerank", "score_confidence")

    g.add_conditional_edges(
        "score_confidence",
        _route_confidence,
        {"answer": "answer", "escalate": "escalate", "abstain": "abstain"},
    )

    g.add_edge("escalate", "retrieve")   # loop back
    g.add_edge("answer", END)
    g.add_edge("abstain", END)

    return g.compile()


# Module-level compiled graph
rag_graph = build_graph()


def run(question: str, active_lang_codes: list[str] | None = None) -> RAGState:
    """Run the full pipeline and return the final state."""
    init: RAGState = {
        "question": question,
        "active_lang_codes": active_lang_codes or ["de", "en"],
        "attempts": 0,
    }
    return rag_graph.invoke(init)
