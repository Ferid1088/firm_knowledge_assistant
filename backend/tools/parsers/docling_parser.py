"""Docling parser — handles A, B, C, E, F, G, H, I (all native-text PDFs)."""
from __future__ import annotations
from backend.tools.parse import make_converter, parse_pdf
from backend.tools.parsers.parse_result import ParseResult

_converter = None


def _get_converter():
    """Return the module-level converter singleton, creating it on first call."""
    global _converter
    if _converter is None:
        _converter = make_converter()
    return _converter


def parse(pdf_path: str, *, reuse_converter: bool = True) -> ParseResult:
    """Parse a native PDF with Docling and return a ParseResult."""
    converter = _get_converter() if reuse_converter else make_converter()
    doc, empty_pages = parse_pdf(pdf_path, converter)
    return ParseResult(
        doc=doc,
        empty_pages=empty_pages,
        parser_type="docling",
        source_path=pdf_path,
    )
