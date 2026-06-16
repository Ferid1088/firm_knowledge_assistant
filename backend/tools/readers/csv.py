"""CSVReaderTool — read CSV files into table + text format."""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from pathlib import Path

from backend.core.tool_base import ToolMetadata
from backend.tools.readers.base import FileReaderTool, RawContent

logger = logging.getLogger(__name__)


class CSVReaderTool(FileReaderTool):
    metadata = ToolMetadata(
        name="reader:csv",
        version="1.0.0",
        tool_type="reader",
        description="Read CSV files into table and plain-text representation",
        dependencies=[],
        capabilities={
            "formats": [".csv", ".CSV"],
            "max_size": 20 * 1024 * 1024,
            "supports_tables": True,
        },
        is_production=True,
        is_async=True,
    )

    supported_extensions = [".csv", ".CSV"]
    format_name = "csv"

    async def execute(self, input_data: str, **kwargs) -> RawContent:
        file_path = str(input_data)
        is_valid, error = await self.validate_input(file_path)
        if not is_valid:
            return RawContent(
                format="csv",
                content="",
                mime_type="text/csv",
                is_corrupted=True,
                warnings=[error],
            )

        try:
            p = Path(file_path)
            raw_bytes = p.read_bytes()

            # Detect encoding
            encoding = "utf-8"
            try:
                raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                encoding = "latin-1"

            text = raw_bytes.decode(encoding)
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)

            table = {
                "rows": len(rows),
                "cols": max((len(r) for r in rows), default=0),
                "data": rows,
            }
            text_repr = "\n".join(" | ".join(row) for row in rows)

            return RawContent(
                format="csv",
                content=text_repr,
                mime_type="text/csv",
                encoding=encoding,
                table_count=1,
                tables=[table],
                file_size=p.stat().st_size,
                modified_time=datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            )

        except Exception as e:
            return self._handle_error(e, file_path)
