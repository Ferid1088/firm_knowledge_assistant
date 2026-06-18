"""FileReaderTool base class, RawContent, and reader-specific exceptions."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from backend.core.tool_base import Tool, ToolMetadata

logger = logging.getLogger(__name__)


# ── Reader-specific exceptions ─────────────────────────────────────────────────

class FileReadError(Exception):
    """Base exception for all file-read failures."""


class UnsupportedFormatError(FileReadError):
    """Raised when the file extension is not supported by this reader."""


class CorruptedFileError(FileReadError):
    """Raised when the file exists but cannot be parsed (corrupted or encrypted)."""


class FileSizeError(FileReadError):
    """Raised when the file exceeds the reader's configured size limit."""


# ── RawContent ─────────────────────────────────────────────────────────────────

@dataclass
class RawContent:
    """Standardized output from all FILE_READERs."""

    # Required
    format: str                              # 'pdf', 'docx', 'xlsx', 'eml', …
    content: Union[str, bytes]               # str for text formats, bytes for binary
    mime_type: str

    # Text encoding
    encoding: str = "utf-8"

    # Counts
    page_count: Optional[int] = None
    table_count: Optional[int] = None
    image_count: Optional[int] = None
    attachment_count: Optional[int] = None

    # Structure
    pages: Optional[List[dict]] = None      # [{number, text, tables, width, height}]
    tables: Optional[List[dict]] = None     # [{rows, cols, data}]
    emails: Optional[List[dict]] = None     # [{from, to, subject, date, body}]
    sections: Optional[List[dict]] = None   # [{level, text, position}]

    # Quality
    extraction_confidence: float = 1.0
    is_encrypted: bool = False
    is_corrupted: bool = False
    warnings: List[str] = field(default_factory=list)

    # File info — 0 / "" sentinel when not determinable
    file_size: int = 0
    modified_time: str = ""


# ── FileReaderTool ─────────────────────────────────────────────────────────────

class FileReaderTool(Tool):
    """Base class for all FILE_READER tools."""

    supported_extensions: List[str] = []
    format_name: str = ""

    def __init__(self, max_file_size: int = 100 * 1024 * 1024):
        """Set the per-instance max_file_size limit used by validate_input()."""
        super().__init__()
        self.max_file_size = max_file_size

    async def validate_input(self, file_path) -> tuple[bool, Optional[str]]:
        """Validate in spec order: exists → extension → size → is_file."""
        path = Path(str(file_path))
        if not path.exists():
            return False, f"File not found: {file_path}"
        if path.suffix.lower() not in [e.lower() for e in self.supported_extensions]:
            return False, f"Unsupported extension '{path.suffix}' for {self.metadata.name}"
        size = path.stat().st_size
        if size > self.max_file_size:
            return False, f"File too large: {size} bytes (max {self.max_file_size})"
        if not path.is_file():
            return False, f"Not a file: {file_path}"
        return True, None

    async def execute(self, input_data, **kwargs) -> RawContent:
        """Subclasses must override this to parse the file and return a RawContent."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement execute()")

    def _handle_error(self, error: Exception, context: str = "") -> RawContent:
        """Return a corrupted RawContent for any unrecoverable read error."""
        logger.error(f"[{self.metadata.name}] Error reading {context}: {error}")
        p = Path(context) if context else None
        return RawContent(
            format=self.format_name,
            content="",
            mime_type="application/octet-stream",
            is_corrupted=True,
            warnings=[str(error)],
            file_size=p.stat().st_size if (p and p.exists()) else 0,
        )
