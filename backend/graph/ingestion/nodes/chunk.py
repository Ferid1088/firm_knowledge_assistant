"""Node: chunk — structural chunking with type-aware handler."""
from __future__ import annotations

from backend.graph.ingestion.state import IngestionState


def chunk_node(state: IngestionState) -> IngestionState:
    from backend.tools.type_registry import get_handler, handler_info
    from backend.tools.chunk import classify_table_role

    resolved_type = state["resolved_type"]
    handler = get_handler(resolved_type)

    if state.get("parse_result"):
        # Normal text path — parse_result from our parsers
        chunks = handler.chunk(state["parse_result"])
    elif state.get("docling_doc"):
        # OCR path — we have a DoclingDocument, need to wrap it
        from backend.tools.parsers.parse_result import ParseResult
        pr = ParseResult(
            doc=state["docling_doc"],
            empty_pages=state.get("empty_pages", []),
            parser_type="ocr",
            source_path=state["source_path"],
        )
        chunks = handler.chunk(pr)
    else:
        return {**state, "error": "No parse result or docling_doc in state"}

    leaf_chunks = [c for c in chunks if c.is_leaf]

    dept_ids = state.get("department_ids", [])
    doc_type_id = state.get("doc_type_id") or state.get("resolved_type")
    table_schemas = handler.table_schemas

    info = handler_info(resolved_type)
    for ch in chunks:
        ch.metadata.setdefault("doc_type", resolved_type)
        ch.metadata.setdefault("doc_type_id", doc_type_id)
        ch.metadata.setdefault("embed_strategy", info["embed_strategy"])
        ch.metadata["department_ids"] = dept_ids
        ch.metadata["structural_type"] = ch.chunk_type
        if ch.chunk_type == "table":
            headers = ch.metadata.get("table_structure", {}).get("headers", [])
            ch.metadata["table_role"] = classify_table_role(headers, table_schemas)

    # Propagate OCR review flag
    ocr_meta = state.get("ocr_meta")
    if ocr_meta and ocr_meta.get("needs_review"):
        for c in leaf_chunks:
            c.metadata["ocr_needs_review"] = True

    # Extract and normalize dates for every leaf chunk
    from backend.tools.dates import extract_and_normalize, date_range

    for ch in leaf_chunks:
        dates = extract_and_normalize(ch.text)
        ch.metadata["dates_iso"] = dates
        dmin, dmax = date_range(dates)
        ch.metadata["date_min"] = dmin
        ch.metadata["date_max"] = dmax

    return {**state, "chunks": chunks, "leaf_chunks": leaf_chunks}
