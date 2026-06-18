"""ODTReaderTool — extract text and tables from OpenDocument Text files via odfpy."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from backend.core.tool_base import ToolMetadata
from backend.tools.readers.base import FileReaderTool, RawContent

logger = logging.getLogger(__name__)


class ODTReaderTool(FileReaderTool):
    """Extract paragraphs, headings, and tables from ODT files via odfpy."""

    metadata = ToolMetadata(
        name="reader:odt",
        version="1.0.0",
        tool_type="reader",
        description="Extract text and tables from OpenDocument Text (.odt) files",
        dependencies=["odfpy>=1.4"],
        capabilities={
            "formats": [".odt", ".ODT"],
            "max_size": 50 * 1024 * 1024,
            "supports_tables": True,
        },
        is_production=True,
        is_async=True,
    )

    supported_extensions = [".odt", ".ODT"]
    format_name = "odt"

    def _validate_dependencies(self) -> None:
        """Check that odfpy is installed (pip name 'odfpy', import name 'odf')."""
        # pip: odfpy, import: odf
        import importlib
        try:
            importlib.import_module("odf")
        except ImportError:
            raise ImportError(
                f"Tool '{self.metadata.name}' requires 'odfpy>=1.4'. "
                "Install with: uv pip install odfpy"
            )

    async def execute(self, input_data: str, **kwargs) -> RawContent:
        """Parse the ODT file and return paragraphs, headings, and tables."""
        file_path = str(input_data)
        is_valid, error = await self.validate_input(file_path)
        if not is_valid:
            return RawContent(
                format="odt",
                content="",
                mime_type="application/vnd.oasis.opendocument.text",
                is_corrupted=True,
                warnings=[error],
            )

        try:
            from odf.opendocument import load
            from odf.text import P, H
            from odf.table import Table, TableRow, TableCell

            doc = load(file_path)
            text_parts = []
            tables_data = []
            sections = []

            for elem in doc.text.childNodes:
                tag = elem.__class__.__name__
                if tag == "P":
                    t = str(elem).strip()
                    if t:
                        text_parts.append(t)
                elif tag == "H":
                    t = str(elem).strip()
                    level = int(elem.getAttribute("text:outline-level") or 1)
                    if t:
                        sections.append({"level": level, "text": t, "position": len(text_parts)})
                        text_parts.append(t)
                elif tag == "Table":
                    rows_data = []
                    for row in elem.childNodes:
                        if row.__class__.__name__ == "TableRow":
                            cells = [str(c).strip() for c in row.childNodes
                                     if c.__class__.__name__ == "TableCell"]
                            rows_data.append(cells)
                    tables_data.append({
                        "rows": len(rows_data),
                        "cols": max((len(r) for r in rows_data), default=0),
                        "data": rows_data,
                    })
                    text_parts.append("--- Table ---")
                    for row in rows_data:
                        text_parts.append(" | ".join(row))

            p = Path(file_path)
            return RawContent(
                format="odt",
                content="\n".join(text_parts),
                mime_type="application/vnd.oasis.opendocument.text",
                table_count=len(tables_data),
                tables=tables_data,
                sections=sections,
                file_size=p.stat().st_size,
                modified_time=datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            )

        except Exception as e:
            return self._handle_error(e, file_path)
