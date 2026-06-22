"""Build and compile the LangGraph RAG pipeline."""
from __future__ import annotations
from langgraph.graph import StateGraph, END

from backend.graph.retrieval.state import RAGState
from backend.graph.retrieval.nodes import (
    prepare_query, retrieve, rerank, expand_context,
    score_confidence, escalate, answer, abstain,
)
from backend.config import MAX_ATTEMPTS, CONFIDENCE_THRESHOLD, CONFIDENCE_GAP_MIN


def _route_confidence(state: RAGState) -> str:
    """Router: direct the graph to answer, escalate, or abstain.

    - answer   : top-1 confidence meets the threshold AND gap is sufficient.
    - escalate : below threshold (or gap too narrow) and attempts remain.
    - abstain  : attempts exhausted — emit a "cannot ground" response.
    """
    conf = state.get("confidence", 0.0)
    gap = state.get("confidence_gap", 0.0)
    attempts = state.get("attempts", 0)

    if conf >= CONFIDENCE_THRESHOLD:
        # Even above the confidence threshold, a narrow gap between top-1 and
        # top-2 indicates ambiguity -- escalate if we still have attempts left.
        if gap < CONFIDENCE_GAP_MIN and attempts < MAX_ATTEMPTS:
            return "escalate"
        return "answer"
    if attempts < MAX_ATTEMPTS:
        return "escalate"
    return "abstain"


def build_graph():
    """Assemble and compile the LangGraph RAG pipeline.

    Topology:
        prepare_query -> retrieve -> rerank -> expand_context -> score_confidence
            -> answer    (confidence OK)
            -> escalate  -> retrieve  (loop, bounded by MAX_ATTEMPTS)
            -> abstain   (attempts exhausted)
    """
    g = StateGraph(RAGState)

    g.add_node("prepare_query", prepare_query)
    g.add_node("retrieve", retrieve)
    g.add_node("rerank", rerank)
    g.add_node("expand_context", expand_context)
    g.add_node("score_confidence", score_confidence)
    g.add_node("escalate", escalate)
    g.add_node("answer", answer)
    g.add_node("abstain", abstain)

    g.set_entry_point("prepare_query")

    g.add_edge("prepare_query", "retrieve")
    g.add_edge("retrieve", "rerank")
    g.add_edge("rerank", "expand_context")
    g.add_edge("expand_context", "score_confidence")

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


def run(question: str, active_lang_codes: list[str] | None = None,
        history: list[dict] | None = None,
        allowed_doc_type_ids: list[str] | None = None,
        structural_types: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None) -> RAGState:
    """Run the full pipeline and return the final state."""
    init: RAGState = {
        "question": question,
        "active_lang_codes": active_lang_codes or ["de", "en"],
        "attempts": 0,
        "history": history or [],
        "allowed_doc_type_ids": allowed_doc_type_ids,
        "structural_types": structural_types,
        "date_filter_from": date_from,
        "date_filter_to": date_to,
    }
    return rag_graph.invoke(init)
