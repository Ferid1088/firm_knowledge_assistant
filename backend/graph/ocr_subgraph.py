"""OCR subgraph — separate compiled LangGraph for scanned document processing.

Invoked by the ingestion graph when triage detects no usable text layer.
Retry/escalation loop: EasyOCR → Tesseract, with resolution bump.

Contract with parent:
    in:  {"source_path": str, "is_image": bool, "ocr_lang": list[str],
          "attempt": 0, "images_scale": float}
    out: {"docling_doc": DoclingDocument, "engine": str, "attempt": int,
          "low_confidence_pages": list[int], "total_pages": int,
          "needs_review": bool}
"""
from __future__ import annotations

import logging
import re
from typing import Any, TypedDict

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
    OCR_MAX_ATTEMPTS,
    OCR_DEFAULT_ENGINE,
    OCR_LOW_DENSITY_CHARS_PER_PAGE,
    OCR_RETRY_WORTHWHILE_RATIO,
    OCR_SMALL_DOC_PAGE_COUNT,
    OCR_BASE_IMAGES_SCALE,
    OCR_ESCALATED_SCALE_CAP,
)

log = logging.getLogger("ingestion.ocr")


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


def escalate_node(state: OCRState) -> OCRState:
    next_engine = "tesseract" if state.get("engine", OCR_DEFAULT_ENGINE) == "easyocr" else "easyocr"
    next_scale = min(
        state.get("images_scale", OCR_BASE_IMAGES_SCALE) * 1.5,
        OCR_ESCALATED_SCALE_CAP,
    )
    return {**state, "engine": next_engine, "images_scale": next_scale}


def flag_for_review_node(state: OCRState) -> OCRState:
    log.warning("Flagging %s for review: %d/%d pages low-density after %d attempts",
                state["source_path"], len(state.get("low_confidence_pages", [])),
                state.get("total_pages", 0), state.get("attempt", 0))
    return {**state, "needs_review": True}


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
