"""EML parser — J: email_thread (native .eml / .msg files).

For PDF printouts of email threads, the docling_parser handles them and
ThreadChunker splits by email boundaries in the extracted text.

For native .eml files (future extension point):
  - Parse with Python's email.message_from_file
  - Return ParseResult(doc=message, parser_type="eml", ...)

Pilot note: the ingest endpoint currently only accepts PDFs. This parser is
the stub for when the endpoint is extended to .eml. PDF-based email threads
flow through docling_parser + ThreadChunker.
"""
from __future__ import annotations
import email
from pathlib import Path

from backend.tools.parsers.parse_result import ParseResult


class EmlParserError(RuntimeError):
    """Raised when an EML file cannot be parsed or has the wrong format."""


def parse(file_path: str) -> ParseResult:
    """Parse a native .eml or .msg file and return a ParseResult with the message object."""
    path = Path(file_path)
    if path.suffix.lower() not in (".eml", ".msg"):
        raise EmlParserError(
            f"EML parser received a non-EML file: {file_path}. "
            "PDF email printouts should use the docling parser."
        )
    with open(file_path, "rb") as f:
        msg = email.message_from_binary_file(f)

    return ParseResult(
        doc=msg,
        empty_pages=[],
        parser_type="eml",
        source_path=file_path,
        extra={"subject": msg.get("Subject", ""), "from": msg.get("From", "")},
    )
