"""Scan-detector tool: determine if a PDF is scanned (no extractable text layer).

Returns a ScanResult with:
  - is_scanned: True if the majority of pages lack a text layer
  - empty_pages: list of 1-based page numbers with < _MIN_TEXT_CHARS chars
  - total_pages: total page count
  - scanned_ratio: fraction of pages that are empty

Callers use is_scanned to decide whether to quarantine the document (do_ocr=False
path) or forward it to the future OCR path.
"""
from __future__ import annotations
from dataclasses import dataclass

import pypdfium2 as pdfium

_MIN_TEXT_CHARS = 20
_SCAN_THRESHOLD = 0.5  # majority-empty -> scanned


@dataclass
class ScanResult:
    is_scanned: bool
    empty_pages: list[int]   # 1-based
    total_pages: int
    scanned_ratio: float


def detect_scan(pdf_path: str) -> ScanResult:
    """Inspect the PDF's text layer page by page and return a ScanResult."""
    pdf = pdfium.PdfDocument(pdf_path)
    total = len(pdf)
    empty: list[int] = []
    for i in range(total):
        page = pdf[i]
        text = page.get_textpage().get_text_range()
        if len(text.strip()) < _MIN_TEXT_CHARS:
            empty.append(i + 1)
    pdf.close()

    ratio = len(empty) / total if total > 0 else 1.0
    return ScanResult(
        is_scanned=ratio >= _SCAN_THRESHOLD,
        empty_pages=empty,
        total_pages=total,
        scanned_ratio=ratio,
    )
