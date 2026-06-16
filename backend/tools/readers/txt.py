"""TextReaderTool — read plain text, Markdown, and HTML files."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from backend.core.tool_base import ToolMetadata
from backend.tools.readers.base import FileReaderTool, RawContent

logger = logging.getLogger(__name__)

_MIME = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
}

_FMT = {
    ".txt": "txt",
    ".md": "md",
    ".html": "html",
    ".htm": "html",
}


class TextReaderTool(FileReaderTool):
    metadata = ToolMetadata(
        name="reader:txt",
        version="1.0.0",
        tool_type="reader",
        description="Read plain text, Markdown, and HTML files",
        dependencies=[],
        capabilities={
            "formats": [".txt", ".md", ".html", ".htm", ".TXT", ".MD"],
            "max_size": 10 * 1024 * 1024,
        },
        is_production=True,
        is_async=True,
    )

    supported_extensions = [".txt", ".md", ".html", ".htm", ".TXT", ".MD"]
    format_name = "txt"   # fallback only; execute() uses the actual extension

    async def execute(self, input_data: str, **kwargs) -> RawContent:
        file_path = str(input_data)
        p = Path(file_path)
        # Resolve actual format before any error path so _handle_error returns
        # the right format string instead of the class-level "txt" fallback.
        actual_fmt = _FMT.get(p.suffix.lower(), "txt")

        is_valid, error = await self.validate_input(file_path)
        if not is_valid:
            return RawContent(
                format=actual_fmt,
                content="",
                mime_type=_MIME.get(p.suffix.lower(), "text/plain"),
                is_corrupted=True,
                warnings=[error],
            )

        try:
            raw_bytes = p.read_bytes()
            encoding = "utf-8"
            try:
                text = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                encoding = "latin-1"
                text = raw_bytes.decode("latin-1")

            mime = _MIME.get(p.suffix.lower(), "text/plain")

            return RawContent(
                format=actual_fmt,
                content=text,
                mime_type=mime,
                encoding=encoding,
                file_size=p.stat().st_size,
                modified_time=datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            )

        except Exception as e:
            # Temporarily set format_name so _handle_error picks up the right format
            self.format_name = actual_fmt
            result = self._handle_error(e, file_path)
            self.format_name = "txt"
            return result
