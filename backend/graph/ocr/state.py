"""State definition for the OCR subgraph."""
from __future__ import annotations
from typing import Any, TypedDict


class OCRState(TypedDict, total=False):
    source_path: str
    is_image: bool
    ocr_lang: list[str]
    engine: str
    attempt: int
    images_scale: float
    docling_doc: Any
    low_confidence_pages: list[int]
    total_pages: int
    needs_review: bool
