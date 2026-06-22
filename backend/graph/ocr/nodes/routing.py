"""Routing functions for the OCR subgraph."""
from __future__ import annotations

from backend.config import (
    OCR_MAX_ATTEMPTS,
    OCR_SMALL_DOC_PAGE_COUNT,
    OCR_RETRY_WORTHWHILE_RATIO,
)
from backend.graph.ocr.state import OCRState


def _retry_worthwhile(state: OCRState) -> bool:
    total = state.get("total_pages", 0)
    low = len(state.get("low_confidence_pages", []))
    if total == 0:
        return bool(low)
    if total <= OCR_SMALL_DOC_PAGE_COUNT:
        return True
    return (low / total) >= OCR_RETRY_WORTHWHILE_RATIO


def _route_after_ocr(state: OCRState) -> str:
    if state.get("needs_review"):
        return "give_up"
    if not state.get("low_confidence_pages"):
        return "done"
    if state["attempt"] >= OCR_MAX_ATTEMPTS:
        return "give_up"
    if not _retry_worthwhile(state):
        return "give_up"
    return "retry"
