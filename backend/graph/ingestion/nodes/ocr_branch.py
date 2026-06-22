"""Node: ocr_branch — delegates to the OCR subgraph for scanned documents."""
from __future__ import annotations

from pathlib import Path

from backend.config import OCR_LANGS, OCR_BASE_IMAGES_SCALE
from backend.graph.ingestion.state import IngestionState


def ocr_branch_node(state: IngestionState) -> IngestionState:
    from backend.graph.ocr import build_ocr_subgraph

    ocr_graph = build_ocr_subgraph()
    sub_out = ocr_graph.invoke({
        "source_path": state["source_path"],
        "is_image": state.get("is_image", False),
        "ocr_lang": OCR_LANGS,
        "attempt": 0,
        "images_scale": OCR_BASE_IMAGES_SCALE,
    }, config={"recursion_limit": 10})

    doc_id = Path(state["source_path"]).stem
    from backend.tools.parse import store_original
    store_original(state["source_path"], doc_id)

    # After OCR, we still need type detection and chunking.
    # Use the OCR parse result but route through standard type detection.
    doc_type_id = state.get("doc_type_id")
    if doc_type_id:
        resolved_type = doc_type_id
        type_confidence = 1.0
    else:
        from backend.tools.type_detector import detect_type
        tr = detect_type(state["source_path"])
        resolved_type = tr.doc_type
        type_confidence = tr.confidence

    from backend.tools.type_registry import handler_info
    info = handler_info(resolved_type)

    return {
        **state,
        "doc_id": doc_id,
        "docling_doc": sub_out.get("docling_doc"),
        "resolved_type": resolved_type,
        "type_confidence": type_confidence,
        "parser_name": "OCR (" + sub_out.get("engine", "easyocr") + ")",
        "chunker_name": info["chunker"],
        "ocr_meta": {
            "engine": sub_out.get("engine", "easyocr"),
            "attempts": sub_out.get("attempt"),
            "low_confidence_pages": sub_out.get("low_confidence_pages", []),
            "total_pages": sub_out.get("total_pages", 0),
            "needs_review": sub_out.get("needs_review", False),
        },
        "empty_pages": sub_out.get("low_confidence_pages", []),
        "is_scanned_result": True,
    }
