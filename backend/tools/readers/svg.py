"""SVGReaderTool — extract text content from SVG files via stdlib xml.etree."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from backend.core.tool_base import ToolMetadata
from backend.tools.readers.base import FileReaderTool, RawContent

logger = logging.getLogger(__name__)

_SVG_NS = "http://www.w3.org/2000/svg"


class SVGReaderTool(FileReaderTool):
    metadata = ToolMetadata(
        name="reader:svg",
        version="1.0.0",
        tool_type="reader",
        description="Extract text content from SVG vector graphics files",
        dependencies=[],   # stdlib only
        capabilities={
            "formats": [".svg", ".SVG"],
            "max_size": 10 * 1024 * 1024,
        },
        is_production=True,
        is_async=True,
    )

    supported_extensions = [".svg", ".SVG"]
    format_name = "svg"

    async def execute(self, input_data: str, **kwargs) -> RawContent:
        file_path = str(input_data)
        is_valid, error = await self.validate_input(file_path)
        if not is_valid:
            return RawContent(
                format="svg",
                content="",
                mime_type="image/svg+xml",
                is_corrupted=True,
                warnings=[error],
            )

        try:
            tree = ET.parse(file_path)
            root = tree.getroot()

            text_parts = []
            for elem in root.iter():
                tag = elem.tag.replace(f"{{{_SVG_NS}}}", "")
                if tag in ("text", "tspan", "title", "desc"):
                    t = (elem.text or "").strip()
                    if t:
                        text_parts.append(t)
                    t = (elem.tail or "").strip()
                    if t:
                        text_parts.append(t)

            p = Path(file_path)
            return RawContent(
                format="svg",
                content="\n".join(text_parts),
                mime_type="image/svg+xml",
                image_count=1,
                file_size=p.stat().st_size,
                modified_time=datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            )

        except ET.ParseError as e:
            return RawContent(
                format="svg",
                content="",
                mime_type="image/svg+xml",
                is_corrupted=True,
                warnings=[f"SVG parse error: {e}"],
            )
        except Exception as e:
            return self._handle_error(e, file_path)
