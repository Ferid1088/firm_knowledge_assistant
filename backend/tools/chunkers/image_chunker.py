"""ImageChunker — scanned_image.

Reached only if the OCR parser successfully extracts text from a scanned PDF.
Takes OCR text (plain string) and windows it with token-aware splitting.

Pilot: always raises because the OCR parser is not yet built.
"""
from __future__ import annotations
import uuid

from backend.tools.chunk import StructuralChunk, _split_by_tokens, CHUNK_MAX_TOKENS
from backend.tools.parsers.parse_result import ParseResult


def chunk(result: ParseResult) -> list[StructuralChunk]:
    if result.parser_type != "ocr":
        raise RuntimeError(
            "ImageChunker received a non-OCR ParseResult. "
            "Route scanned_image documents through the OCR parser."
        )

    text: str = result.doc or ""
    if not text.strip():
        return []

    out: list[StructuralChunk] = []
    for i, seg in enumerate(_split_by_tokens(text, CHUNK_MAX_TOKENS)):
        out.append(StructuralChunk(
            chunk_id=str(uuid.uuid4()), chunk_type="prose", is_leaf=True,
            text=seg, context_text=seg, parent_id=None,
            heading_path=[], doc_items=[], chunk_index_in_parent=i,
            metadata={"ocr": True},
        ))
    return out
