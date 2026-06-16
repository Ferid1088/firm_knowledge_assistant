"""DXFReaderTool — extract entities and text from AutoCAD DXF files via ezdxf."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from backend.core.tool_base import ToolMetadata
from backend.tools.readers.base import FileReaderTool, RawContent

logger = logging.getLogger(__name__)


class DXFReaderTool(FileReaderTool):
    metadata = ToolMetadata(
        name="reader:dxf",
        version="1.0.0",
        tool_type="reader",
        description="Extract text entities and structure from AutoCAD DXF files",
        dependencies=["ezdxf>=0.18"],
        capabilities={
            "formats": [".dxf", ".DXF"],
            "max_size": 100 * 1024 * 1024,
        },
        is_production=True,
        is_async=True,
    )

    supported_extensions = [".dxf", ".DXF"]
    format_name = "dxf"

    async def execute(self, input_data: str, **kwargs) -> RawContent:
        file_path = str(input_data)
        is_valid, error = await self.validate_input(file_path)
        if not is_valid:
            return RawContent(
                format="dxf",
                content="",
                mime_type="application/dxf",
                is_corrupted=True,
                warnings=[error],
            )

        try:
            import ezdxf

            doc = ezdxf.readfile(file_path)
            text_parts = []

            for entity in doc.modelspace():
                dxftype = entity.dxftype()
                if dxftype == "TEXT":
                    t = entity.dxf.text.strip()
                    if t:
                        text_parts.append(t)
                elif dxftype == "MTEXT":
                    t = entity.plain_mtext().strip()
                    if t:
                        text_parts.append(t)

            p = Path(file_path)
            return RawContent(
                format="dxf",
                content="\n".join(text_parts),
                mime_type="application/dxf",
                file_size=p.stat().st_size,
                modified_time=datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            )

        except Exception as e:
            return self._handle_error(e, file_path)
