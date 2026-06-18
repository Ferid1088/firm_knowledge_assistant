"""OCR parser — D: scanned_image.

Pilot status: QUARANTINED. OCR (Tesseract/Vision) path is designed but not yet
built ("scanned/handwritten/drawings — OUT now, designed-for").
Raises OcrNotBuiltError so the pipeline can surface a clear error, not a crash.

To enable: install pytesseract + poppler, set OCR_ENABLED=True in config, and
replace the body of parse() with the Tesseract/Docling-OCR path.
"""
from __future__ import annotations
from backend.tools.parsers.parse_result import ParseResult


class OcrNotBuiltError(RuntimeError):
    """Raised when a scanned PDF is submitted and the OCR path is not yet built."""


def parse(pdf_path: str) -> ParseResult:
    """Raise OcrNotBuiltError — OCR path is not yet implemented for the pilot."""
    raise OcrNotBuiltError(
        "Document type 'scanned_image' requires the OCR pipeline (Tesseract / "
        "Docling with do_ocr=True), which is not yet built for this pilot. "
        "Please re-scan the document as a native PDF, or wait for the OCR path."
    )
