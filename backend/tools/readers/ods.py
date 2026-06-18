"""ODSReaderTool — extract tables from OpenDocument Spreadsheet files via odfpy."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from backend.core.tool_base import ToolMetadata
from backend.tools.readers.base import FileReaderTool, RawContent

logger = logging.getLogger(__name__)


class ODSReaderTool(FileReaderTool):
    """Extract sheets and cell values from ODS spreadsheet files via odfpy."""

    metadata = ToolMetadata(
        name="reader:ods",
        version="1.0.0",
        tool_type="reader",
        description="Extract tables from OpenDocument Spreadsheet (.ods) files",
        dependencies=["odfpy>=1.4"],
        capabilities={
            "formats": [".ods", ".ODS"],
            "max_size": 50 * 1024 * 1024,
            "supports_tables": True,
            "supports_multiple_sheets": True,
        },
        is_production=True,
        is_async=True,
    )

    supported_extensions = [".ods", ".ODS"]
    format_name = "ods"

    def _validate_dependencies(self) -> None:
        """Check that odfpy is installed (pip name 'odfpy', import name 'odf')."""
        import importlib
        try:
            importlib.import_module("odf")
        except ImportError:
            raise ImportError(
                f"Tool '{self.metadata.name}' requires 'odfpy>=1.4'. "
                "Install with: pip install odfpy"
            )

    async def execute(self, input_data: str, **kwargs) -> RawContent:
        """Iterate all Table sheets in the ODS file and return cell data as table dicts."""
        file_path = str(input_data)
        is_valid, error = await self.validate_input(file_path)
        if not is_valid:
            return RawContent(
                format="ods",
                content="",
                mime_type="application/vnd.oasis.opendocument.spreadsheet",
                is_corrupted=True,
                warnings=[error],
            )

        try:
            from odf.opendocument import load
            from odf.table import Table, TableRow, TableCell

            doc = load(file_path)
            tables_data = []
            text_parts = []

            for sheet in doc.spreadsheet.childNodes:
                if sheet.__class__.__name__ != "Table":
                    continue
                sheet_name = sheet.getAttribute("table:name") or "Sheet"
                rows_data = []
                for row in sheet.childNodes:
                    if row.__class__.__name__ != "TableRow":
                        continue
                    cells = []
                    for cell in row.childNodes:
                        if cell.__class__.__name__ == "TableCell":
                            cells.append(str(cell).strip())
                    if any(cells):
                        rows_data.append(cells)

                tables_data.append({
                    "sheet": sheet_name,
                    "rows": len(rows_data),
                    "cols": max((len(r) for r in rows_data), default=0),
                    "data": rows_data,
                })
                text_parts.append(f"=== Sheet: {sheet_name} ===")
                for row in rows_data:
                    text_parts.append(" | ".join(row))

            p = Path(file_path)
            return RawContent(
                format="ods",
                content="\n".join(text_parts),
                mime_type="application/vnd.oasis.opendocument.spreadsheet",
                table_count=len(tables_data),
                tables=tables_data,
                file_size=p.stat().st_size,
                modified_time=datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            )

        except Exception as e:
            return self._handle_error(e, file_path)
