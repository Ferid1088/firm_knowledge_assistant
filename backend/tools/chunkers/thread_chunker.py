"""ThreadChunker — J: email_thread.

Handles two cases:
  1. PDF printout of an email thread → Docling extracts text, we split by
     email boundaries detected in the prose
  2. Native .eml (future) → split email.Message by MIME parts

Email boundary detection in PDF-extracted text:
  "Von: / From:", "An: / To:", "Datum: / Date:", "Betreff: / Subject:"
  appearing together within a short span signal a new email.

Each email message becomes an atomic leaf (chunk_type="email_message") with
metadata: from, to, date, subject extracted from the header lines.
"""
from __future__ import annotations
import re
import uuid
from docling_core.types.doc import DocItemLabel

from backend.tools.chunk import StructuralChunk
from backend.tools.parsers.parse_result import ParseResult

_HEADER_KEYS = re.compile(
    r"^(Von|From|An|To|CC|BCC|Datum|Date|Gesendet|Sent|Betreff|Subject)\s*:",
    re.IGNORECASE | re.MULTILINE,
)
_FROM_RE = re.compile(r"(?:Von|From)\s*:\s*(.+)", re.IGNORECASE)
_DATE_RE = re.compile(r"(?:Datum|Date|Gesendet|Sent)\s*:\s*(.+)", re.IGNORECASE)
_SUBJ_RE = re.compile(r"(?:Betreff|Subject)\s*:\s*(.+)", re.IGNORECASE)
_TO_RE = re.compile(r"(?:An|To)\s*:\s*(.+)", re.IGNORECASE)

# Minimum header-key density to consider a text block an email header
_HEADER_DENSITY_THRESHOLD = 2  # at least 2 header keys in block


def _looks_like_header(text: str) -> bool:
    return len(_HEADER_KEYS.findall(text)) >= _HEADER_DENSITY_THRESHOLD


def _extract_email_meta(text: str) -> dict:
    return {
        "from":    (m.group(1).strip() if (m := _FROM_RE.search(text)) else ""),
        "to":      (m.group(1).strip() if (m := _TO_RE.search(text)) else ""),
        "date":    (m.group(1).strip() if (m := _DATE_RE.search(text)) else ""),
        "subject": (m.group(1).strip() if (m := _SUBJ_RE.search(text)) else ""),
    }


def _chunk_docling(doc) -> list[StructuralChunk]:
    """Split Docling-parsed text into email messages by header detection."""
    out: list[StructuralChunk] = []
    current_blocks: list[tuple] = []
    counter = 0
    heading_path: list[str] = []
    parent_id: str | None = None

    def flush_email(blocks):
        nonlocal counter, parent_id
        if not blocks:
            return
        full_text = "\n".join(getattr(item, "text", "") or "" for item, _ in blocks).strip()
        if not full_text:
            return
        meta = _extract_email_meta(full_text)
        subject = meta.get("subject") or f"Email {counter + 1}"
        # The first block may be the header; rest is body
        ctx = subject
        if heading_path:
            ctx = " > ".join(heading_path) + " > " + subject
        out.append(StructuralChunk(
            chunk_id=str(uuid.uuid4()), chunk_type="email_message", is_leaf=True,
            text=full_text,
            context_text=f"{ctx}\n\n{full_text}".strip(),
            parent_id=parent_id,
            heading_path=list(heading_path) + [subject],
            doc_items=[item for item, _ in blocks],
            chunk_index_in_parent=counter,
            metadata=meta,
        ))
        counter += 1

    try:
        items = list(doc.iterate_items())
    except Exception:
        return out

    for item, level in items:
        label = getattr(item, "label", None)
        text = getattr(item, "text", "") or ""

        if label in (DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE):
            flush_email(current_blocks)
            current_blocks = []
            if level is not None and isinstance(level, int):
                heading_path = heading_path[:max(0, level - 1)]
            heading_path.append(text.strip())
            cid = str(uuid.uuid4())
            out.append(StructuralChunk(
                chunk_id=cid, chunk_type="heading", is_leaf=False,
                text=text, context_text=text, parent_id=parent_id,
                heading_path=list(heading_path), doc_items=[item],
                chunk_index_in_parent=counter,
            ))
            counter += 1
            parent_id = cid

        elif text.strip():
            if _looks_like_header(text) and current_blocks:
                # New email starts here
                flush_email(current_blocks)
                current_blocks = [(item, level)]
            else:
                current_blocks.append((item, level))

    flush_email(current_blocks)
    return out


def _chunk_eml(result: ParseResult) -> list[StructuralChunk]:
    """Split a native email.Message into parts."""
    import email as email_lib
    msg = result.doc
    out: list[StructuralChunk] = []

    def _walk(msg, depth=0):
        if msg.is_multipart():
            for part in msg.get_payload(decode=False):
                _walk(part, depth + 1)
        else:
            payload = msg.get_payload(decode=True)
            if payload is None:
                return
            try:
                text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                return
            if not text.strip():
                return
            meta = {
                "from": msg.get("From", ""),
                "to": msg.get("To", ""),
                "date": msg.get("Date", ""),
                "subject": msg.get("Subject", ""),
            }
            subject = meta["subject"] or "Email"
            out.append(StructuralChunk(
                chunk_id=str(uuid.uuid4()), chunk_type="email_message", is_leaf=True,
                text=text, context_text=f"{subject}\n\n{text}".strip(),
                parent_id=None, heading_path=[subject], doc_items=[],
                chunk_index_in_parent=len(out), metadata=meta,
            ))

    _walk(msg)
    return out


def chunk(result: ParseResult) -> list[StructuralChunk]:
    if result.parser_type == "eml":
        return _chunk_eml(result)
    return _chunk_docling(result.doc)
