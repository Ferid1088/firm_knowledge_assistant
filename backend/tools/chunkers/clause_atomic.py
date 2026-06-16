"""ClauseAtomic chunker — E: legal_contract.

Legal contracts are structured as Articles / Clauses / Numbered paragraphs.
Every numbered clause is an atomic leaf — splitting mid-clause destroys meaning.

Clause-detection patterns (deliberately broad; tune per contract family):
  §  1 / § 1.2           German/Swiss legal paragraph
  Art. 5 / Article 5     EU/international
  Clause 3.1             Anglo-Saxon
  (1) / (a) / 1.         Numbered sub-paragraphs
  WHEREAS / NOW THEREFORE Preamble
  Roman: I., II., III.

Hierarchy:
  heading / article title → parent node
  clause / sub-clause     → atomic leaf (chunk_type="clause")
  tables (exhibits)       → atomic leaf (chunk_type="table")
  preamble prose          → windowed prose leaf
"""
from __future__ import annotations
import re
import uuid
from docling_core.types.doc import DocItemLabel

from backend.tools.chunk import StructuralChunk
from backend.tools.parsers.parse_result import ParseResult

_CLAUSE_PATTERNS = [
    re.compile(r"^\s*§\s*\d+", re.MULTILINE),
    re.compile(r"^\s*(Art\.|Article|Artikel)\s+\d+", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*(Clause|Abschnitt|Section|Ziffer)\s+\d+", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*\(\d+\)\s"),
    re.compile(r"^\s*\(\s*[a-zA-Z]\s*\)\s"),
    re.compile(r"^\s*(I{1,3}V?|VI{0,3}|IX|XI{0,3})\.\s+\w"),  # Roman numerals
    re.compile(r"^\s*(WHEREAS|NOW\s+THEREFORE|RECITALS?)\b", re.IGNORECASE),
]


def _is_clause(text: str) -> bool:
    return any(p.search(text) for p in _CLAUSE_PATTERNS)


def _heading_path_str(path: list[str]) -> str:
    return " > ".join(path) if path else ""


def chunk(result: ParseResult) -> list[StructuralChunk]:
    doc = result.doc
    out: list[StructuralChunk] = []
    heading_path: list[str] = []
    parent_id: str | None = None
    prose_buf: list[tuple] = []
    counter = 0

    def flush_prose():
        nonlocal counter
        for item, hp in prose_buf:
            text = getattr(item, "text", "") or ""
            if not text.strip():
                continue
            ctx = _heading_path_str(hp)
            context_text = f"{ctx}\n\n{text}".strip() if ctx else text
            out.append(StructuralChunk(
                chunk_id=str(uuid.uuid4()), chunk_type="prose", is_leaf=True,
                text=text, context_text=context_text, parent_id=parent_id,
                heading_path=list(hp), doc_items=[item],
                chunk_index_in_parent=counter,
            ))
            counter += 1
        prose_buf.clear()

    try:
        items = list(doc.iterate_items())
    except Exception:
        return out

    for item, level in items:
        label = getattr(item, "label", None)
        text = getattr(item, "text", "") or ""

        if label in (DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE):
            flush_prose()
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

        elif label == DocItemLabel.TABLE:
            flush_prose()
            try:
                md = item.export_to_markdown(doc=doc)
            except Exception:
                md = text or ""
            if not md.strip():
                continue
            ctx = _heading_path_str(heading_path)
            context_text = f"{ctx}\n\n{md}".strip() if ctx else md
            out.append(StructuralChunk(
                chunk_id=str(uuid.uuid4()), chunk_type="table", is_leaf=True,
                text=md, context_text=context_text, parent_id=parent_id,
                heading_path=list(heading_path), doc_items=[item],
                chunk_index_in_parent=counter,
            ))
            counter += 1

        elif label in (DocItemLabel.TEXT, DocItemLabel.PARAGRAPH,
                       DocItemLabel.LIST_ITEM) and text.strip():
            if _is_clause(text):
                flush_prose()
                ctx = _heading_path_str(heading_path)
                context_text = f"{ctx}\n\n{text}".strip() if ctx else text
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type="clause", is_leaf=True,
                    text=text, context_text=context_text, parent_id=parent_id,
                    heading_path=list(heading_path), doc_items=[item],
                    chunk_index_in_parent=counter,
                ))
                counter += 1
            else:
                prose_buf.append((item, list(heading_path)))

        elif text.strip():
            prose_buf.append((item, list(heading_path)))

    flush_prose()
    return out
