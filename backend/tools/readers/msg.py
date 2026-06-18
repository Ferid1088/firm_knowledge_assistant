"""MSGReaderTool — read Outlook MSG files via extract-msg."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from backend.core.tool_base import ToolMetadata
from backend.tools.readers.base import FileReaderTool, RawContent

logger = logging.getLogger(__name__)


class MSGReaderTool(FileReaderTool):
    """Read Outlook MSG files and extract subject, body, and metadata via extract-msg."""

    metadata = ToolMetadata(
        name="reader:msg",
        version="1.0.0",
        tool_type="reader",
        description="Read Outlook MSG files and extract message content",
        dependencies=["extract-msg>=0.28"],
        capabilities={
            "formats": [".msg", ".MSG"],
            "max_size": 25 * 1024 * 1024,
            "supports_attachments": True,
        },
        is_production=True,
        is_async=True,
    )

    supported_extensions = [".msg", ".MSG"]
    format_name = "msg"

    def _validate_dependencies(self) -> None:
        """Verify extract-msg is installed (pip name 'extract-msg', imports as 'extract_msg')."""
        # pip: extract-msg, import: extract_msg
        import importlib
        try:
            importlib.import_module("extract_msg")
        except ImportError:
            raise ImportError(
                f"Tool '{self.metadata.name}' requires 'extract-msg>=0.28'. "
                "Install with: uv pip install extract-msg"
            )

    async def execute(self, input_data: str, **kwargs) -> RawContent:
        """Open the MSG file with extract-msg and return structured email content."""
        file_path = str(input_data)
        is_valid, error = await self.validate_input(file_path)
        if not is_valid:
            return RawContent(
                format="msg",
                content="",
                mime_type="application/vnd.ms-outlook",
                is_corrupted=True,
                warnings=[error],
            )

        try:
            import extract_msg

            msg = extract_msg.Message(file_path)
            subject = msg.subject or ""
            from_addr = msg.sender or ""
            to_addr = msg.to or ""
            date = str(msg.date) if msg.date else ""
            body = msg.body or ""

            attachments = []
            for att in (msg.attachments or []):
                attachments.append(att.longFilename or att.shortFilename or "attachment")

            emails = [{
                "from": from_addr,
                "to": to_addr,
                "subject": subject,
                "date": date,
                "body": body,
            }]

            text = (
                f"From: {from_addr}\nTo: {to_addr}\nSubject: {subject}\n"
                f"Date: {date}\n\n{body}"
            )

            p = Path(file_path)
            return RawContent(
                format="msg",
                content=text,
                mime_type="application/vnd.ms-outlook",
                emails=emails,
                attachment_count=len(attachments),
                file_size=p.stat().st_size,
                modified_time=datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            )

        except Exception as e:
            return self._handle_error(e, file_path)
