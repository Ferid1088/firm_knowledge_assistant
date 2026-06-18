"""ProjectChunker — G: project_management.

Project management documents mix prose (scope, objectives), structured items
(task lists, responsibility assignments, risk registers) and timeline markers
(dates, deadlines, sprints).

Chunking strategy:
  heading             → parent node
  tables (Gantt, risk, RACI, budget) → atomic leaf (chunk_type="table")
  date-anchored items (tasks with deadlines) → atomic leaf (chunk_type="project_item")
  milestone markers   → atomic leaf (chunk_type="milestone")
  prose descriptions  → windowed prose leaf

The `project_item` and `milestone` chunks carry temporal metadata extracted
by heuristic regex into chunk.metadata["dates"] so that temporal-sparse
embedding (future GPU path) can index them by date.
"""
from __future__ import annotations
import re
import uuid
from docling_core.types.doc import DocItemLabel

from backend.tools.chunk import StructuralChunk, extract_table_structure
from backend.tools.parsers.parse_result import ParseResult

_DATE_PATTERN = re.compile(
    r"\b(?:"
    r"\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}"
    r"|\d{4}[.\-/]\d{2}[.\-/]\d{2}"
    r"|Q[1-4]\s+\d{4}"
    r"|KW\s*\d{1,2}"
    r"|(?:Jan|Feb|Mar|Apr|Mai|May|Jun|Jul|Aug|Sep|Oct|Okt|Nov|Dez|Dec)\w*[\s,]+\d{4}"
    r")\b",
    re.IGNORECASE,
)
_MILESTONE_PATTERN = re.compile(
    r"\b(Milestone|Meilenstein|M\d+|Sprint\s+\d+|Phase\s+\d+|Go-?Live|Launch|Release)\b",
    re.IGNORECASE,
)


def _extract_dates(text: str) -> list[str]:
    """Return all date strings found in text using the date regex."""
    return [m.group(0) for m in _DATE_PATTERN.finditer(text)]


def _heading_path_str(path: list[str]) -> str:
    """Render heading path as breadcrumb string."""
    return " > ".join(path) if path else ""


def chunk(result: ParseResult) -> list[StructuralChunk]:
    """Split project documents into milestone/project_item leaves, table leaves, and prose."""
    doc = result.doc
    out: list[StructuralChunk] = []
    heading_path: list[str] = []
    parent_id: str | None = None
    prose_buf: list[tuple] = []
    counter = 0

    def flush_prose():
        """Emit prose StructuralChunks for every buffered item, then clear the buffer."""
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
                metadata={"dates": _extract_dates(text)},
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
            dates = _extract_dates(md)
            tbl_struct = extract_table_structure(item)
            out.append(StructuralChunk(
                chunk_id=str(uuid.uuid4()), chunk_type="table", is_leaf=True,
                text=md, context_text=context_text, parent_id=parent_id,
                heading_path=list(heading_path), doc_items=[item],
                chunk_index_in_parent=counter,
                metadata={"dates": dates, "table_structure": tbl_struct},
            ))
            counter += 1

        elif label in (DocItemLabel.TEXT, DocItemLabel.PARAGRAPH,
                       DocItemLabel.LIST_ITEM) and text.strip():
            dates = _extract_dates(text)
            is_milestone = bool(_MILESTONE_PATTERN.search(text))
            has_date = bool(dates)

            if is_milestone or has_date:
                flush_prose()
                chunk_type = "milestone" if is_milestone else "project_item"
                ctx = _heading_path_str(heading_path)
                context_text = f"{ctx}\n\n{text}".strip() if ctx else text
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type=chunk_type, is_leaf=True,
                    text=text, context_text=context_text, parent_id=parent_id,
                    heading_path=list(heading_path), doc_items=[item],
                    chunk_index_in_parent=counter,
                    metadata={"dates": dates},
                ))
                counter += 1
            else:
                prose_buf.append((item, list(heading_path)))

        elif text.strip():
            prose_buf.append((item, list(heading_path)))

    flush_prose()
    return out
