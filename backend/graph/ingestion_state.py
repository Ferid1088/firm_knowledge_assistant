"""State definition for the ingestion LangGraph pipeline."""
from __future__ import annotations
from typing import Any, Optional, TypedDict


class IngestionState(TypedDict, total=False):
    # Input
    source_path: str
    doc_type_id: Optional[str]
    department_ids: list[str]
    verbose: bool
    persist_dir: str

    # Triage
    is_scanned: bool
    is_image: bool

    # Type detection
    resolved_type: str
    type_confidence: float

    # Parse
    parse_result: Any          # ParseResult from our parsers
    docling_doc: Any           # DoclingDocument (set by OCR branch or text_parse)
    ocr_meta: dict[str, Any]   # set only when OCR subgraph ran

    # Chunks
    chunks: list[Any]          # StructuralChunk list from our chunkers
    leaf_chunks: list[Any]     # filtered leaves ready for embedding
    bm25_indices: dict[str, Any]

    # Images (VLM enrichment)
    extracted_images: list[dict]
    vlm_chunks: list[dict]

    # Result
    n_chunks: int
    doc_id: str
    is_scanned_result: bool
    empty_pages: list[int]
    parser_name: str
    chunker_name: str
    error: Optional[str]
