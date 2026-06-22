"""Node: escalate — switch OCR engine or bump resolution."""
from __future__ import annotations

import logging
import shutil

from backend.config import OCR_DEFAULT_ENGINE, OCR_BASE_IMAGES_SCALE, OCR_ESCALATED_SCALE_CAP
from backend.graph.ocr.state import OCRState

log = logging.getLogger("ingestion.ocr")


def escalate_node(state: OCRState) -> OCRState:
    current_engine = state.get("engine", OCR_DEFAULT_ENGINE)
    next_scale = min(
        state.get("images_scale", OCR_BASE_IMAGES_SCALE) * 1.5,
        OCR_ESCALATED_SCALE_CAP,
    )

    # Only escalate to tesseract if the binary is installed; otherwise just
    # bump resolution and keep the current engine.
    if current_engine == "easyocr" and shutil.which("tesseract") is not None:
        next_engine = "tesseract"
    elif current_engine == "easyocr":
        log.warning("tesseract-ocr not installed — skipping engine escalation, bumping resolution only")
        next_engine = "easyocr"
    else:
        next_engine = "easyocr"

    return {**state, "engine": next_engine, "images_scale": next_scale}
