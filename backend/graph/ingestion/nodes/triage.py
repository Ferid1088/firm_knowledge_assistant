"""Node: triage — detect whether the input is scanned/image and route accordingly."""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF — for triage text-layer check

from backend.graph.ingestion.state import IngestionState

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def _has_text_layer(pdf_path: str, min_chars: int | None = None) -> bool:
    if min_chars is None:
        from backend.config import TEXT_LAYER_MIN_CHARS
        min_chars = TEXT_LAYER_MIN_CHARS
    try:
        with fitz.open(pdf_path) as doc:
            chars = sum(len(page.get_text("text")) for page in doc)
            return chars >= min_chars
    except Exception:
        return False


def triage_node(state: IngestionState) -> IngestionState:
    src = state["source_path"]
    suffix = Path(src).suffix.lower()

    if suffix in IMAGE_EXTENSIONS:
        return {**state, "is_scanned": True, "is_image": True}
    if suffix == ".pdf":
        return {**state, "is_scanned": not _has_text_layer(src), "is_image": False}
    return {**state, "is_scanned": False, "is_image": False}


def _route_after_triage(state: IngestionState) -> str:
    return "ocr" if state.get("is_scanned") else "text"
