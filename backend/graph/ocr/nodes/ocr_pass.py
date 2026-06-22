"""Node: ocr_pass — run OCR conversion on scanned documents."""
from __future__ import annotations

import logging
import re
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    EasyOcrOptions,
    PdfPipelineOptions,
    TesseractCliOcrOptions,
)
from docling.document_converter import (
    DocumentConverter,
    ImageFormatOption,
    PdfFormatOption,
)

from backend.config import (
    OCR_DEFAULT_ENGINE,
    OCR_LOW_DENSITY_CHARS_PER_PAGE,
    OCR_BASE_IMAGES_SCALE,
)
from backend.graph.ocr.state import OCRState

log = logging.getLogger("ingestion.ocr")


def _build_converter(state: OCRState) -> DocumentConverter:
    engine = state.get("engine", OCR_DEFAULT_ENGINE)
    lang = state.get("ocr_lang", ["de", "en"])

    ocr_options = (
        TesseractCliOcrOptions(lang=lang)
        if engine == "tesseract"
        else EasyOcrOptions(lang=lang)
    )

    opts = PdfPipelineOptions()
    opts.do_ocr = True
    opts.ocr_options = ocr_options
    opts.do_table_structure = True
    opts.generate_page_images = True
    opts.generate_picture_images = True
    opts.images_scale = state.get("images_scale", OCR_BASE_IMAGES_SCALE)

    if state.get("is_image"):
        return DocumentConverter(
            format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=opts)}
        )
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )


def _page_confidence_scan(doc: Any) -> tuple[list[int], int]:
    low: list[int] = []
    try:
        pages = list(doc.pages.items())
    except AttributeError:
        return low, 0
    for page_no, page in pages:
        text = page.export_to_text() if hasattr(page, "export_to_text") else ""
        char_count = len(re.sub(r"\s+", "", text))
        if char_count < OCR_LOW_DENSITY_CHARS_PER_PAGE:
            low.append(page_no)
    return low, len(pages)


def ocr_pass_node(state: OCRState) -> OCRState:
    attempt = state.get("attempt", 0)
    try:
        converter = _build_converter(state)
        result = converter.convert(state["source_path"])
        doc = result.document
    except Exception as e:
        if attempt == 0:
            raise
        log.error("OCR retry (engine=%s) failed: %s", state.get("engine"), e)
        return {**state, "attempt": attempt + 1, "needs_review": True}

    low_pages, total_pages = _page_confidence_scan(doc)
    log.info("OCR pass %d (engine=%s): %d/%d low-density pages",
             attempt, state.get("engine", OCR_DEFAULT_ENGINE), len(low_pages), total_pages)

    return {
        **state,
        "attempt": attempt + 1,
        "docling_doc": doc,
        "low_confidence_pages": low_pages,
        "total_pages": total_pages,
    }
