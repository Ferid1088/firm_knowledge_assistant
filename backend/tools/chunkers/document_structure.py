"""DocumentStructureChunker — authority_document, norm_standard, technical_manual.

Strict decimal section numbering: 1, 1.1, 1.1.1. Each numbered section is an
atomic leaf preserving the full section as the smallest retrievable unit.

Hierarchy:
  Numbered heading 1.1.1 → leaf (section with body merged in)
  Unnumbered headings → parent nodes
  Tables → atomic leaves (chunk_type="table")
  Figures → atomic leaves (chunk_type="figure")
  Formulas → atomic leaves (chunk_type="formula")
  Lists → grouped atomic leaves (chunk_type="list")
"""
from __future__ import annotations
import re
import uuid
from docling_core.types.doc import DocItemLabel

from backend.tools.chunk import (
    StructuralChunk, extract_table_structure, _make_context, _heading_path_str,
    _split_by_tokens, _HEADING_LABELS, _PICTURE_LABELS, _CAPTION_LABELS,
    _FORMULA_LABELS, _CODE_LABELS, CHUNK_MAX_TOKENS,
)
from backend.tools.parsers.parse_result import ParseResult

_NUMBERED_HEADING = re.compile(r"^\s*([A-Z]|\d+)(\.\d+)*\.?\s+\w")


def chunk(result: ParseResult) -> list[StructuralChunk]:
    doc = result.doc
    out: list[StructuralChunk] = []
    heading_path: list[str] = []
    parent_id: str | None = None
    counter = 0
    current_section: dict | None = None
    list_buf: list[tuple] = []
    last_caption = ""

    def close_section():
        nonlocal counter
        if current_section is None:
            return
        text = current_section["text"]
        if not text.strip():
            return
        hp = current_section["heading_path"]
        for seg in _split_by_tokens(text, CHUNK_MAX_TOKENS):
            out.append(StructuralChunk(
                chunk_id=str(uuid.uuid4()), chunk_type="section", is_leaf=True,
                text=seg, context_text=_make_context(hp, seg),
                parent_id=current_section["parent_id"], heading_path=list(hp),
                doc_items=current_section["doc_items"],
                chunk_index_in_parent=counter,
            ))
            counter += 1

    def flush_list():
        nonlocal counter
        if not list_buf:
            return
        texts, items = [], []
        for li_item, li_hp in list_buf:
            t = getattr(li_item, "text", "") or ""
            if t.strip():
                texts.append(f"• {t.strip()}")
                items.append(li_item)
        if not texts:
            list_buf.clear()
            return
        text = "\n".join(texts)
        hp = list_buf[0][1]
        out.append(StructuralChunk(
            chunk_id=str(uuid.uuid4()), chunk_type="list", is_leaf=True,
            text=text, context_text=_make_context(hp, text),
            parent_id=parent_id, heading_path=list(hp), doc_items=items,
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

        if label in _HEADING_LABELS:
            close_section()
            current_section = None
            flush_list()
            if level is not None and isinstance(level, int):
                heading_path = heading_path[:max(0, level - 1)]
            heading_path.append(text.strip())

            if _NUMBERED_HEADING.match(text):
                cid = str(uuid.uuid4())
                current_section = {
                    "cid": cid, "text": text.strip(),
                    "heading_path": list(heading_path), "parent_id": parent_id,
                    "doc_items": [item], "index": counter,
                }
                counter += 1
                parent_id = cid
            else:
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
            flush_list()
            try:
                md = item.export_to_markdown(doc=doc)
            except Exception:
                md = text or ""
            if not md.strip():
                continue
            tbl_struct = extract_table_structure(item)
            meta = {"table_structure": tbl_struct}
            if last_caption:
                meta["caption"] = last_caption
                last_caption = ""
            out.append(StructuralChunk(
                chunk_id=str(uuid.uuid4()), chunk_type="table", is_leaf=True,
                text=md, context_text=_make_context(heading_path, md),
                parent_id=parent_id, heading_path=list(heading_path),
                doc_items=[item], chunk_index_in_parent=counter,
                metadata=meta,
            ))
            counter += 1

        elif _PICTURE_LABELS and label in _PICTURE_LABELS:
            close_section()
            current_section = None
            flush_list()
            caption = last_caption or text or ""
            last_caption = ""
            fig_text = f"[Figure: {caption}]" if caption else "[Figure]"
            out.append(StructuralChunk(
                chunk_id=str(uuid.uuid4()), chunk_type="figure", is_leaf=True,
                text=fig_text, context_text=_make_context(heading_path, fig_text),
                parent_id=parent_id, heading_path=list(heading_path),
                doc_items=[item], chunk_index_in_parent=counter,
                metadata={"caption": caption, "needs_description": True},
            ))
            counter += 1

        elif _CAPTION_LABELS and label in _CAPTION_LABELS:
            last_caption = text.strip()
            if out and out[-1].chunk_type in ("figure", "table"):
                out[-1].metadata["caption"] = last_caption
                last_caption = ""

        elif _FORMULA_LABELS and label in _FORMULA_LABELS:
            close_section()
            current_section = None
            flush_list()
            if text.strip():
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type="formula", is_leaf=True,
                    text=text, context_text=_make_context(heading_path, text),
                    parent_id=parent_id, heading_path=list(heading_path),
                    doc_items=[item], chunk_index_in_parent=counter,
                ))
                counter += 1

        elif label == DocItemLabel.LIST_ITEM:
            if current_section is not None:
                current_section["text"] += "\n• " + text
                current_section["doc_items"].append(item)
            elif text.strip():
                list_buf.append((item, list(heading_path)))

        elif text.strip():
            flush_list()
            if current_section is not None:
                current_section["text"] += "\n" + text
                current_section["doc_items"].append(item)
            else:
                ctx = _make_context(heading_path, text)
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type="prose", is_leaf=True,
                    text=text, context_text=ctx, parent_id=parent_id,
                    heading_path=list(heading_path), doc_items=[item],
                    chunk_index_in_parent=counter,
                ))
                counter += 1

    close_section()
    flush_list()
    return out
