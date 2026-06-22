"""Build and compile the LangGraph ingestion pipeline."""
from __future__ import annotations

import threading
from pathlib import Path

from backend.config import QDRANT_DIR
from backend.graph.ingestion.state import IngestionState
from backend.graph.ingestion.nodes import (
    triage_node, _route_after_triage,
    text_parse_node, ocr_branch_node,
    chunk_node, lang_detect_node, bm25_node,
    enrich_node, quality_gate_node, embed_store_node,
)


def build_ingestion_graph():
    from langgraph.graph import StateGraph, START, END

    g = StateGraph(IngestionState)
    g.add_node("triage", triage_node)
    g.add_node("text_parse", text_parse_node)
    g.add_node("ocr_branch", ocr_branch_node)
    g.add_node("chunk", chunk_node)
    g.add_node("lang_detect", lang_detect_node)
    g.add_node("bm25", bm25_node)
    g.add_node("enrich", enrich_node)
    g.add_node("quality_gate", quality_gate_node)
    g.add_node("embed_store", embed_store_node)

    g.add_edge(START, "triage")
    g.add_conditional_edges(
        "triage", _route_after_triage,
        {"ocr": "ocr_branch", "text": "text_parse"},
    )
    g.add_edge("text_parse", "chunk")
    g.add_edge("ocr_branch", "chunk")
    g.add_conditional_edges(
        "chunk",
        lambda s: "end" if s.get("error") else "continue",
        {"end": END, "continue": "lang_detect"},
    )
    g.add_edge("lang_detect", "bm25")
    g.add_edge("bm25", "enrich")
    g.add_edge("enrich", "quality_gate")
    g.add_edge("quality_gate", "embed_store")
    g.add_edge("embed_store", END)
    return g.compile()


# -- Public API ------------------------------------------------------------

_compiled_graph = None
_graph_lock = threading.Lock()


def run_ingest(
    source_path: str,
    persist_dir: str = QDRANT_DIR,
    verbose: bool = True,
    doc_type_id: str | None = None,
    department_ids: list[str] | None = None,
) -> IngestionState:
    """Run the ingestion graph and return the final state."""
    global _compiled_graph
    if _compiled_graph is None:
        with _graph_lock:
            if _compiled_graph is None:
                _compiled_graph = build_ingestion_graph()

    init: IngestionState = {
        "source_path": str(Path(source_path).resolve()),
        "doc_type_id": doc_type_id,
        "department_ids": department_ids or [],
        "verbose": verbose,
        "persist_dir": persist_dir,
    }
    return _compiled_graph.invoke(init)
