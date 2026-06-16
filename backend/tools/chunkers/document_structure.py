"""DocumentStructureChunker — F: authority_document.

Authority documents (DIN/ISO norms, regulations, official guidelines) have a
strict decimal section numbering system: 1, 1.1, 1.1.1, 1.1.1.1.

Each numbered section is an atomic leaf preserving the full section as the
smallest retrievable unit. This is critical for standards: retrieving § 3.2.1
without the rest of § 3.2 loses normative context.

The chunk stores the FULL section text (heading + body) so that RAG can cite
"according to § 3.2.1 — Measurement conditions…" with the complete text.

Hierarchy:
  Numbered heading 1. → parent
    Numbered heading 1.1 → parent
      Numbered heading 1.1.1 → leaf (section with body)
      Body text under 1.1.1 → merged INTO the 1.1.1 leaf
  Unnumbered headings → parent nodes
  Tables → atomic leaves (chunk_type="table")
"""
from __future__ import annotations
import re
import uuid
from docling_core.types.doc import DocItemLabel

from backend.tools.chunk import StructuralChunk
from backend.tools.parsers.parse_result import ParseResult

# Matches: "3.", "3.2", "3.2.1", "A.1", "A.1.2"
_NUMBERED_HEADING = re.compile(r"^\s*([A-Z]|\d+)(\.\d+)*\.?\s+\w")


def _heading_path_str(path: list[str]) -> str:
    return " > ".join(path) if path else ""


def chunk(result: ParseResult) -> list[StructuralChunk]:
    doc = result.doc
    out: list[StructuralChunk] = []
    heading_path: list[str] = []
    parent_id: str | None = None
    counter = 0

    # Current section accumulator: when we encounter a numbered heading,
    # we open a section; all body text is merged into it until the next heading.
    current_section: dict | None = None

    def close_section():
        nonlocal counter
        if current_section is None:
            return
        text = current_section["text"]
        if not text.strip():
            return
        ctx = _heading_path_str(current_section["heading_path"])
        context_text = f"{ctx}\n\n{text}".strip() if ctx else text
        out.append(StructuralChunk(
            chunk_id=current_section["cid"],
            chunk_type="section",
            is_leaf=True,
            text=text,
            context_text=context_text,
            parent_id=current_section["parent_id"],
            heading_path=list(current_section["heading_path"]),
            doc_items=current_section["doc_items"],
            chunk_index_in_parent=current_section["index"],
        ))

    try:
        items = list(doc.iterate_items())
    except Exception:
        return out

    for item, level in items:
        label = getattr(item, "label", None)
        text = getattr(item, "text", "") or ""

        if label in (DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE):
            close_section()
            current_section = None

            if level is not None and isinstance(level, int):
                heading_path = heading_path[:max(0, level - 1)]
            heading_path.append(text.strip())

            if _NUMBERED_HEADING.match(text):
                # Numbered heading → open a section leaf (body merges in below)
                cid = str(uuid.uuid4())
                current_section = {
                    "cid": cid, "text": text.strip(),
                    "heading_path": list(heading_path),
                    "parent_id": parent_id,
                    "doc_items": [item],
                    "index": counter,
                }
                counter += 1
                parent_id = cid
            else:
                # Unnumbered heading → pure parent node
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
            close_section()
            current_section = None
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

        elif text.strip():
            if current_section is not None:
                # Merge body text into the open section
                current_section["text"] += "\n" + text
                current_section["doc_items"].append(item)
            else:
                # Orphan prose (before first numbered heading)
                ctx = _heading_path_str(heading_path)
                context_text = f"{ctx}\n\n{text}".strip() if ctx else text
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type="prose", is_leaf=True,
                    text=text, context_text=context_text, parent_id=parent_id,
                    heading_path=list(heading_path), doc_items=[item],
                    chunk_index_in_parent=counter,
                ))
                counter += 1

    close_section()
    return out
