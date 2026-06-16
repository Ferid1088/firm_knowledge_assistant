"""EMLReaderTool — parse .eml files into structured email content."""
from __future__ import annotations

import email
import email.policy
import logging
from datetime import datetime
from pathlib import Path

from backend.core.tool_base import ToolMetadata
from backend.tools.readers.base import FileReaderTool, RawContent

logger = logging.getLogger(__name__)


class EMLReaderTool(FileReaderTool):
    metadata = ToolMetadata(
        name="reader:eml",
        version="1.0.0",
        tool_type="reader",
        description="Parse EML email files into structured content",
        dependencies=[],
        capabilities={
            "formats": [".eml", ".EML"],
            "max_size": 50 * 1024 * 1024,
            "supports_attachments": True,
        },
        is_production=True,
        is_async=True,
    )

    supported_extensions = [".eml", ".EML"]
    format_name = "eml"

    async def execute(self, input_data: str, **kwargs) -> RawContent:
        file_path = str(input_data)
        is_valid, error = await self.validate_input(file_path)
        if not is_valid:
            return RawContent(
                format="eml",
                content="",
                mime_type="message/rfc822",
                is_corrupted=True,
                warnings=[error],
            )

        try:
            p = Path(file_path)
            raw = p.read_bytes()
            msg = email.message_from_bytes(raw, policy=email.policy.default)

            body_parts = []
            attachment_count = 0

            for part in msg.walk():
                ct = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in disposition:
                    attachment_count += 1
                    continue
                if ct == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            body_parts.append(payload.decode(charset))
                        except Exception:
                            body_parts.append(payload.decode("latin-1", errors="replace"))

            body = "\n".join(body_parts)
            em = {
                "from": str(msg.get("From", "")),
                "to": str(msg.get("To", "")),
                "subject": str(msg.get("Subject", "")),
                "date": str(msg.get("Date", "")),
                "body": body,
            }
            text = (
                f"From: {em['from']}\nTo: {em['to']}\n"
                f"Subject: {em['subject']}\nDate: {em['date']}\n\n{body}"
            )

            return RawContent(
                format="eml",
                content=text,
                mime_type="message/rfc822",
                attachment_count=attachment_count,
                emails=[em],
                file_size=p.stat().st_size,
                modified_time=datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            )

        except Exception as e:
            return self._handle_error(e, file_path)
