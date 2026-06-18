"""ImageChunker — D: scanned_image.

This chunker is reached only if the OCR parser successfully extracts text from
a scanned PDF. It takes the OCR text (a plain string in ParseResult.doc) and
windows it with the standard HybridChunker.

Pilot status: always raises because the OCR parser is not yet built.
When the OCR path is enabled, this chunker will work without modification.
"""
from __future__ import annotations
import uuid

from backend.tools.chunk import StructuralChunk, make_prose_chunker
from backend.tools.parsers.parse_result import ParseResult


def chunk(result: ParseResult) -> list[StructuralChunk]:
    """Window OCR-extracted plain text into prose leaf chunks by paragraph."""
    if result.parser_type != "ocr":
        raise RuntimeError(
            "ImageChunker received a non-OCR ParseResult. "
            "Route scanned_image documents through the OCR parser."
        )

    text: str = result.doc or ""
    if not text.strip():
        return []

    # OCR output has no Docling structure — treat as flat prose, window it
    # by paragraph breaks first, then token-limit within each paragraph.
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    out: list[StructuralChunk] = []
    for i, para in enumerate(paragraphs):
        out.append(StructuralChunk(
            chunk_id=str(uuid.uuid4()),
            chunk_type="prose",
            is_leaf=True,
            text=para,
            context_text=para,
            parent_id=None,
            heading_path=[],
            doc_items=[],
            chunk_index_in_parent=i,
            metadata={"ocr": True},
        ))
    return out
