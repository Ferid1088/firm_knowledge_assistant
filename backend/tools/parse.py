"""Parse native PDFs with Docling's default TableFormer pipeline (no VLM, no OCR).

Scanned-PDF guard: pages with no extractable text are quarantined — never indexed silently.
"""
from __future__ import annotations
import shutil
from pathlib import Path

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
import pypdfium2 as pdfium

from backend.config import ORIGINALS_DIR

# Minimum characters per page to consider it "has a text layer"
_MIN_TEXT_CHARS = 20


def make_converter() -> DocumentConverter:
    opts = PdfPipelineOptions()
    opts.do_table_structure = True
    opts.table_structure_options.mode = TableFormerMode.ACCURATE
    opts.do_ocr = False  # native text layer only — flip True only for scans (future path)
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )


def check_text_layer(pdf_path: str) -> tuple[bool, list[int]]:
    """Return (has_text, empty_pages). Empty pages have < _MIN_TEXT_CHARS extractable chars."""
    pdf = pdfium.PdfDocument(pdf_path)
    empty_pages = []
    for i in range(len(pdf)):
        page = pdf[i]
        text = page.get_textpage().get_text_range()
        if len(text.strip()) < _MIN_TEXT_CHARS:
            empty_pages.append(i + 1)  # 1-based
    pdf.close()
    return len(empty_pages) == 0, empty_pages


def store_original(pdf_path: str, doc_id: str) -> str:
    """Copy the source PDF into the originals store. Returns destination path.

    Re-ingesting a doc_id overwrites the stored original with the new version
    (the new version's chunks supersede the old via is_current, see backend.services.store).
    """
    dest = Path(ORIGINALS_DIR) / f"{doc_id}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if Path(pdf_path).resolve() != dest.resolve():
        shutil.copy2(pdf_path, dest)
    return str(dest)


def parse_pdf(pdf_path: str, converter: DocumentConverter | None = None):
    """Return (DoclingDocument, empty_pages). Caller decides whether to quarantine."""
    converter = converter or make_converter()
    _, empty_pages = check_text_layer(pdf_path)
    doc = converter.convert(pdf_path).document
    return doc, empty_pages
