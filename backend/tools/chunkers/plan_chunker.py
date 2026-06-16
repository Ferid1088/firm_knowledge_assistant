"""PlanChunker — C: technical_plan.

Technical plans are structured as Phases → Work Packages → Tasks / Milestones.

Chunking strategy:
  - Top-level headings (Phase / WP) → parent nodes
  - Numbered tasks / deliverables / milestones → atomic leaves (chunk_type="task")
  - Tables (timelines, responsibility matrices) → atomic leaves (chunk_type="table")
  - Remaining prose (descriptions, notes) → windowed by HybridChunker within phase

Task-detection heuristics (extend for specific plan family):
  - Lines starting with a number + dot/paren: "1.", "1.1", "(a)", "Task 3:"
  - Keywords: "Milestone", "Deliverable", "WP", "AP" (Arbeitspaket), "Aufgabe"
  - Checkbox-like: "[ ]", "☐", "→"
"""
from __future__ import annotations
import re
import uuid
from docling_core.types.doc import DocItemLabel

from backend.tools.chunk import StructuralChunk, make_prose_chunker
from backend.tools.parsers.parse_result import ParseResult

_TASK_PATTERNS = [
    re.compile(r"^\s*\d+[\.\)]\s+\S"),          # "1. Task name"
    re.compile(r"^\s*\d+\.\d+[\.\)]?\s+\S"),    # "1.1 Sub-task"
    re.compile(r"^\s*\([a-zA-Z]\)\s+\S"),        # "(a) item"
    re.compile(r"^\s*(Task|Milestone|Deliverable|WP|AP|Aufgabe|Meilenstein)\s*\d*\s*[:\-]", re.IGNORECASE),
    re.compile(r"^\s*[☐✓→►•]\s+\S"),            # checkbox / arrow
]


def _is_task(text: str) -> bool:
    return any(p.match(text) for p in _TASK_PATTERNS)


def _heading_path_str(path: list[str]) -> str:
    return " > ".join(path) if path else ""


def chunk(result: ParseResult) -> list[StructuralChunk]:
    doc = result.doc
    prose_chunker = make_prose_chunker()
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
            if _is_task(text):
                flush_prose()
                ctx = _heading_path_str(heading_path)
                context_text = f"{ctx}\n\n{text}".strip() if ctx else text
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type="task", is_leaf=True,
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
