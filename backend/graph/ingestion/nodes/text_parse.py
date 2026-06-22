"""Node: text_parse — existing Docling path for born-digital documents."""
from __future__ import annotations

import logging
from pathlib import Path

from backend.graph.ingestion.state import IngestionState

log = logging.getLogger("ingestion")


def text_parse_node(state: IngestionState) -> IngestionState:
    from backend.tools.type_registry import get_handler
    from backend.tools.scan_detector import detect_scan
    from backend.tools.parse import store_original

    src = state["source_path"]
    doc_id = Path(src).stem
    verbose = state.get("verbose", True)

    # Scan check (belt-and-suspenders — triage already decided, but this
    # gives us empty_pages list for metadata)
    scan = detect_scan(src)
    if scan.empty_pages and verbose:
        log.warning("Pages without text layer: %s", scan.empty_pages)

    # Type detection
    doc_type_id = state.get("doc_type_id")
    if doc_type_id:
        resolved_type = doc_type_id
        type_confidence = 1.0
    else:
        from backend.tools.type_detector import detect_type
        tr = detect_type(src)
        resolved_type = tr.doc_type
        type_confidence = tr.confidence

    handler = get_handler(resolved_type)
    from backend.tools.type_registry import handler_info
    info = handler_info(resolved_type)
    if verbose:
        log.info("type=%s parser=%s chunker=%s", resolved_type, info["parser"], info["chunker"])

    # Parse
    parse_result = handler.parse(src)
    store_original(src, doc_id)

    return {
        **state,
        "doc_id": doc_id,
        "resolved_type": resolved_type,
        "type_confidence": type_confidence,
        "parse_result": parse_result,
        "empty_pages": scan.empty_pages,
        "parser_name": info["parser"],
        "chunker_name": info["chunker"],
        "is_scanned_result": False,
    }
