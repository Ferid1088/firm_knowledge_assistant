"""Node: quality_gate — filter out low-quality chunks before embedding."""
from __future__ import annotations

import logging

from backend.graph.ingestion.state import IngestionState

log = logging.getLogger("ingestion")


def quality_gate_node(state: IngestionState) -> IngestionState:
    leaf_chunks = state.get("leaf_chunks", [])
    before = len(leaf_chunks)
    filtered = [
        c for c in leaf_chunks
        if len(c.text.strip()) >= 10 and c.context_text.strip()
    ]
    dropped = before - len(filtered)
    if dropped:
        log.info("Quality gate: dropped %d/%d chunks", dropped, before)
    return {**state, "leaf_chunks": filtered}
