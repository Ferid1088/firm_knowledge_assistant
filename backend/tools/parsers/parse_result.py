"""Shared ParseResult contract passed from parsers to chunkers."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParseResult:
    """Canonical output of every parser; chunkers consume this."""
    doc: Any                      # DoclingDocument | str (OCR text) | email.Message
    empty_pages: list[int]        # 1-based page numbers with no text
    parser_type: str              # "docling" | "ocr" | "eml"
    source_path: str              # original file path (for page-size lookup)
    extra: dict = field(default_factory=dict)  # parser-specific extras (e.g. OCR confidence)
