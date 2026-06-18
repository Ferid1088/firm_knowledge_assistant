"""ListChunker — adaptive chunking for list-heavy documents.

Treats contiguous LIST_ITEM elements as a single atomic list chunk,
preserving the list structure as one retrieval unit. Isolated list items
that appear between prose are grouped with adjacent items.

Hierarchy:
  heading       → parent node
  table         → atomic leaf (chunk_type="table")
  list group    → atomic leaf (chunk_type="list")
  prose         → leaf (chunk_type="prose")
"""
from __future__ import annotations
import uuid
from docling_core.types.doc import DocItemLabel

from backend.tools.chunk import StructuralChunk, extract_table_structure
from backend.tools.parsers.parse_result import ParseResult


def _heading_path_str(path: list[str]) -> str:
    return " > ".join(path) if path else ""


def chunk(result: ParseResult) -> list[StructuralChunk]:
    """Walk the parsed document; group contiguous list items into atomic list chunks."""
    doc = result.doc
    out: list[StructuralChunk] = []
    heading_path: list[str] = []
    parent_id: str | None = None
    counter = 0

    list_buf: list[tuple] = []  # [(item, heading_path)]

    def flush_list():
        nonlocal counter
        if not list_buf:
            return
        texts = []
        items = []
        for item, _hp in list_buf:
            t = getattr(item, "text", "") or ""
            if t.strip():
                texts.append(f"• {t.strip()}")
                items.append(item)
        if not texts:
            list_buf.clear()
            return
        text = "\n".join(texts)
        hp = list_buf[0][1]
        ctx = _heading_path_str(hp)
        context_text = f"{ctx}\n\n{text}".strip() if ctx else text
        out.append(StructuralChunk(
            chunk_id=str(uuid.uuid4()),
            chunk_type="list",
            is_leaf=True,
            text=text,
            context_text=context_text,
            parent_id=parent_id,
            heading_path=list(hp),
            doc_items=items,
            chunk_index_in_parent=counter,
        ))
        counter += 1
        list_buf.clear()

    try:
        items = list(doc.iterate_items())
    except Exception:
        return out

    for item, level in items:
        label = getattr(item, "label", None)
        text = getattr(item, "text", "") or ""

        if label in (DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE):
            flush_list()
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
            flush_list()
            try:
                md = item.export_to_markdown(doc=doc)
            except Exception:
                md = text or ""
            if not md.strip():
                continue
            ctx = _heading_path_str(heading_path)
            context_text = f"{ctx}\n\n{md}".strip() if ctx else md
            tbl_struct = extract_table_structure(item)
            out.append(StructuralChunk(
                chunk_id=str(uuid.uuid4()), chunk_type="table", is_leaf=True,
                text=md, context_text=context_text, parent_id=parent_id,
                heading_path=list(heading_path), doc_items=[item],
                chunk_index_in_parent=counter,
                metadata={"table_structure": tbl_struct},
            ))
            counter += 1

        elif label == DocItemLabel.LIST_ITEM:
            list_buf.append((item, list(heading_path)))

        elif text.strip():
            flush_list()
            ctx = _heading_path_str(heading_path)
            context_text = f"{ctx}\n\n{text}".strip() if ctx else text
            out.append(StructuralChunk(
                chunk_id=str(uuid.uuid4()), chunk_type="prose", is_leaf=True,
                text=text, context_text=context_text, parent_id=parent_id,
                heading_path=list(heading_path), doc_items=[item],
                chunk_index_in_parent=counter,
            ))
            counter += 1

    flush_list()
    return out
