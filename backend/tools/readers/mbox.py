"""MBOXReaderTool — read MBOX mailbox files via stdlib mailbox."""
from __future__ import annotations

import logging
import mailbox
from datetime import datetime
from pathlib import Path

from backend.core.tool_base import ToolMetadata
from backend.tools.readers.base import FileReaderTool, RawContent

logger = logging.getLogger(__name__)


class MBOXReaderTool(FileReaderTool):
    metadata = ToolMetadata(
        name="reader:mbox",
        version="1.0.0",
        tool_type="reader",
        description="Read MBOX mailbox files and extract individual email messages",
        dependencies=[],   # stdlib only
        capabilities={
            "formats": [".mbox", ".MBOX"],
            "max_size": 200 * 1024 * 1024,
            "supports_attachments": True,
        },
        is_production=True,
        is_async=True,
    )

    supported_extensions = [".mbox", ".MBOX"]
    format_name = "mbox"

    async def execute(self, input_data: str, **kwargs) -> RawContent:
        file_path = str(input_data)
        is_valid, error = await self.validate_input(file_path)
        if not is_valid:
            return RawContent(
                format="mbox",
                content="",
                mime_type="application/mbox",
                is_corrupted=True,
                warnings=[error],
            )

        try:
            mbox = mailbox.mbox(file_path)
            emails = []
            text_parts = []

            for msg in mbox:
                subject = msg.get("Subject", "")
                from_addr = msg.get("From", "")
                to_addr = msg.get("To", "")
                date = msg.get("Date", "")

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            try:
                                body += part.get_payload(decode=True).decode(
                                    part.get_content_charset() or "utf-8", errors="replace"
                                )
                            except Exception:
                                pass
                else:
                    try:
                        body = msg.get_payload(decode=True).decode(
                            msg.get_content_charset() or "utf-8", errors="replace"
                        )
                    except Exception:
                        body = str(msg.get_payload())

                emails.append({
                    "from": from_addr,
                    "to": to_addr,
                    "subject": subject,
                    "date": date,
                    "body": body,
                })
                text_parts.append(
                    f"From: {from_addr}\nTo: {to_addr}\nSubject: {subject}\n"
                    f"Date: {date}\n\n{body}"
                )

            p = Path(file_path)
            return RawContent(
                format="mbox",
                content="\n\n---\n\n".join(text_parts),
                mime_type="application/mbox",
                emails=emails,
                attachment_count=0,
                file_size=p.stat().st_size,
                modified_time=datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            )

        except Exception as e:
            return self._handle_error(e, file_path)
