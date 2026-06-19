"""HybridChunker — default for prose_text, knowledge_base, hr_personnel, report_study, presentation.

Delegates to chunk_document which handles all structural elements:
tables, figures, formulas, lists, and token-windowed prose.
"""
from __future__ import annotations
from backend.tools.chunk import StructuralChunk, chunk_document
from backend.tools.parsers.parse_result import ParseResult


def chunk(result: ParseResult) -> list[StructuralChunk]:
    return chunk_document(result.doc)
