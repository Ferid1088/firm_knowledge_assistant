"""DWGReaderTool — stub for AutoCAD DWG files (no open-source Python parser available)."""
from __future__ import annotations

import logging
from pathlib import Path

from backend.core.tool_base import ToolMetadata
from backend.tools.readers.base import FileReaderTool, RawContent

logger = logging.getLogger(__name__)


class DWGReaderTool(FileReaderTool):
    """Stub reader for AutoCAD DWG binary format.

    No open-source Python library can reliably parse DWG files. This stub
    registers the format so the pipeline recognises .dwg files and surfaces a
    clear error rather than a generic "unsupported format" message. When a
    commercial or open-source DWG parser becomes available, replace the execute()
    body and update dependencies accordingly.
    """

    metadata = ToolMetadata(
        name="reader:dwg",
        version="1.0.0",
        tool_type="reader",
        description="Stub reader for AutoCAD DWG files — no parser available yet",
        dependencies=[],
        capabilities={
            "formats": [".dwg", ".DWG"],
            "max_size": 100 * 1024 * 1024,
        },
        is_production=False,   # stub — disabled in config/tools.yaml
        is_experimental=True,
        is_async=True,
    )

    supported_extensions = [".dwg", ".DWG"]
    format_name = "dwg"

    async def execute(self, input_data: str, **kwargs) -> RawContent:
        file_path = str(input_data)
        p = Path(file_path)
        warning = (
            "DWG format is not yet supported: no open-source Python parser is available. "
            "Convert to DXF and re-ingest, or use a CAD application to export as PDF."
        )
        logger.warning(f"[reader:dwg] {warning} — file: {file_path}")
        return RawContent(
            format="dwg",
            content="",
            mime_type="application/acad",
            is_corrupted=False,
            extraction_confidence=0.0,
            warnings=[warning],
            file_size=p.stat().st_size if p.exists() else 0,
        )
