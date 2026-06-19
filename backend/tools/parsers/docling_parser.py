"""Docling parser — handles all native-text documents (PDF, DOCX, PPTX, HTML, etc.).

Docling's DocumentConverter auto-detects the input format and applies the
appropriate pipeline. TableFormer is enabled for PDF; other formats use
Docling's built-in converters.
"""
from __future__ import annotations
from backend.tools.parse import make_converter, parse_document
from backend.tools.parsers.parse_result import ParseResult

_converter = None


def _get_converter():
    global _converter
    if _converter is None:
        _converter = make_converter()
    return _converter


def parse(file_path: str, *, reuse_converter: bool = True) -> ParseResult:
    """Parse any Docling-supported format and return a ParseResult."""
    converter = _get_converter() if reuse_converter else make_converter()
    doc, empty_pages = parse_document(file_path, converter)
    return ParseResult(
        doc=doc,
        empty_pages=empty_pages,
        parser_type="docling",
        source_path=file_path,
    )
