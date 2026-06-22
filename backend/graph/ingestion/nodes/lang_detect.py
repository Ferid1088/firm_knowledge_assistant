"""Node: lang_detect — detect language for each leaf chunk."""
from __future__ import annotations

from backend.graph.ingestion.state import IngestionState


def lang_detect_node(state: IngestionState) -> IngestionState:
    from backend.tools.pipeline import _detect_lang
    for ch in state.get("leaf_chunks", []):
        ch.metadata["lang"] = _detect_lang(ch.text)
    return state
