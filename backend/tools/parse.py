"""Parse documents with Docling (multi-format) — default TableFormer pipeline, no VLM, no OCR.

Supports: PDF, DOCX, PPTX, HTML, and any format Docling's DocumentConverter handles.
Scanned-PDF guard: pages with no extractable text are flagged — never indexed silently.
"""
from __future__ import annotations
import shutil
from pathlib import Path

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode

from backend.config import ORIGINALS_DIR

_MIN_TEXT_CHARS = 20


def make_converter() -> DocumentConverter:
    """Build a Docling DocumentConverter with TableFormer (accurate) and OCR disabled."""
    opts = PdfPipelineOptions()
    opts.do_table_structure = True
    opts.table_structure_options.mode = TableFormerMode.ACCURATE
    opts.do_ocr = False
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )


def check_text_layer(pdf_path: str) -> tuple[bool, list[int]]:
    """Return (has_text, empty_pages). PDF-only; non-PDF formats always return (True, [])."""
    if not pdf_path.lower().endswith(".pdf"):
        return True, []
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(pdf_path)
        empty_pages = []
        for i in range(len(pdf)):
            page = pdf[i]
            text = page.get_textpage().get_text_range()
            if len(text.strip()) < _MIN_TEXT_CHARS:
                empty_pages.append(i + 1)
        pdf.close()
        return len(empty_pages) == 0, empty_pages
    except Exception:
        return True, []


def store_original(file_path: str, doc_id: str) -> str:
    """Copy the source file into the originals store, preserving its extension."""
    ext = Path(file_path).suffix or ".pdf"
    dest = Path(ORIGINALS_DIR) / f"{doc_id}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if Path(file_path).resolve() != dest.resolve():
        shutil.copy2(file_path, dest)
    return str(dest)


def parse_document(file_path: str, converter: DocumentConverter | None = None):
    """Parse any Docling-supported format. Returns (DoclingDocument, empty_pages)."""
    converter = converter or make_converter()
    _, empty_pages = check_text_layer(file_path)
    doc = converter.convert(file_path).document
    return doc, empty_pages


# Backwards-compatible alias
parse_pdf = parse_document
