"""HybridChunker — A: prose_text, H: knowledge_base, I: hr_personnel.

Thin wrapper around the existing structural parent-child chunker in chunk.py.
Headings anchor sections; prose is windowed by HybridChunker (token-aware);
tables are kept atomic.
"""
from __future__ import annotations
from backend.tools.chunk import StructuralChunk, chunk_document, make_prose_chunker
from backend.tools.parsers.parse_result import ParseResult

_prose_chunker = None


def _get_prose_chunker():
    global _prose_chunker
    if _prose_chunker is None:
        _prose_chunker = make_prose_chunker()
    return _prose_chunker


def chunk(result: ParseResult) -> list[StructuralChunk]:
    return chunk_document(result.doc, _get_prose_chunker())
