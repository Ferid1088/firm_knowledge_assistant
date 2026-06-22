"""Node: flag_for_review — mark document as needing human review."""
from __future__ import annotations

import logging

from backend.graph.ocr.state import OCRState

log = logging.getLogger("ingestion.ocr")


def flag_for_review_node(state: OCRState) -> OCRState:
    log.warning("Flagging %s for review: %d/%d pages low-density after %d attempts",
                state["source_path"], len(state.get("low_confidence_pages", [])),
                state.get("total_pages", 0), state.get("attempt", 0))
    return {**state, "needs_review": True}
