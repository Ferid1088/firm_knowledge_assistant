"""PDFReaderTool — extract text, pages, and tables from PDF files via pdfplumber."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from backend.core.tool_base import ToolMetadata
from backend.tools.readers.base import FileReaderTool, RawContent

logger = logging.getLogger(__name__)


class PDFReaderTool(FileReaderTool):
    """Extract text, pages, and table structure from PDF files."""

    metadata = ToolMetadata(
        name="reader:pdf",
        version="1.0.0",
        tool_type="reader",
        description="Extract text, tables, and structure from PDF files",
        dependencies=["pdfplumber>=0.9.0"],
        capabilities={
            "formats": [".pdf", ".PDF"],
            "max_size": 100 * 1024 * 1024,
            "supports_tables": True,
            "supports_page_detection": True,
            "supports_extraction_confidence": True,
        },
        is_production=True,
        is_async=True,
    )

    supported_extensions = [".pdf", ".PDF"]
    format_name = "pdf"

    async def execute(self, input_data: str, **kwargs) -> RawContent:
        file_path = str(input_data)
        is_valid, error = await self.validate_input(file_path)
        if not is_valid:
            return RawContent(
                format="pdf",
                content="",
                mime_type="application/pdf",
                is_corrupted=True,
                warnings=[error],
                file_size=Path(file_path).stat().st_size if Path(file_path).exists() else 0,
            )

        try:
            import pdfplumber

            with pdfplumber.open(file_path) as pdf:
                page_count = len(pdf.pages)
                confidence = 1.0
                full_text = ""
                pages = []

                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text() or ""
                    # Spec: scanned-page detection requires both text length and a
                    # minimum page width to avoid false positives on narrow pages.
                    if len(page_text or "") < 50 and page.width > 100:
                        confidence = min(confidence, 0.3)

                    raw_tables = page.extract_tables() or []
                    pages.append({
                        "number": i + 1,
                        "text": page_text,
                        "tables": raw_tables,
                        "width": float(page.width),
                        "height": float(page.height),
                    })
                    full_text += f"\n--- Page {i + 1} ---\n{page_text}\n"

                p = Path(file_path)
                mt = datetime.fromtimestamp(p.stat().st_mtime).isoformat()

                logger.info(
                    f"[reader:pdf] {file_path}: {page_count} pages, confidence={confidence:.2f}"
                )

                return RawContent(
                    format="pdf",
                    content=full_text,
                    mime_type="application/pdf",
                    page_count=page_count,
                    table_count=sum(len(pg["tables"]) for pg in pages),
                    pages=pages,
                    extraction_confidence=confidence,
                    file_size=p.stat().st_size,
                    modified_time=mt,
                )

        except Exception as e:
            return self._handle_error(e, file_path)
