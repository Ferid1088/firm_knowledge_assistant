"""Build and compile the OCR subgraph — retry/escalation loop for scanned docs."""
from __future__ import annotations

from backend.graph.ocr.state import OCRState
from backend.graph.ocr.nodes import ocr_pass_node, escalate_node, flag_for_review_node
from backend.graph.ocr.nodes.routing import _route_after_ocr


def build_ocr_subgraph():
    from langgraph.graph import StateGraph, START, END

    g = StateGraph(OCRState)
    g.add_node("ocr_pass", ocr_pass_node)
    g.add_node("escalate", escalate_node)
    g.add_node("flag_for_review", flag_for_review_node)

    g.add_edge(START, "ocr_pass")
    g.add_conditional_edges(
        "ocr_pass", _route_after_ocr,
        {"done": END, "retry": "escalate", "give_up": "flag_for_review"},
    )
    g.add_edge("escalate", "ocr_pass")
    g.add_edge("flag_for_review", END)
    return g.compile()
