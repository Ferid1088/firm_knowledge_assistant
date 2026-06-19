"""ClauseAtomic chunker — legal_contract.

Every numbered clause is an atomic leaf. Tables (exhibits), figures, formulas,
and lists are handled properly. Prose between clauses is token-windowed.
"""
from __future__ import annotations
import re
import uuid
from docling_core.types.doc import DocItemLabel

from backend.tools.chunk import (
    StructuralChunk, extract_table_structure, _make_context, _heading_path_str,
    _split_by_tokens, _HEADING_LABELS, _PICTURE_LABELS, _CAPTION_LABELS,
    _FORMULA_LABELS, CHUNK_MAX_TOKENS,
)
from backend.tools.parsers.parse_result import ParseResult

_CLAUSE_PATTERNS = [
    re.compile(r"^\s*§\s*\d+", re.MULTILINE),
    re.compile(r"^\s*(Art\.|Article|Artikel)\s+\d+", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*(Clause|Abschnitt|Section|Ziffer)\s+\d+", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*\(\d+\)\s"),
    re.compile(r"^\s*\(\s*[a-zA-Z]\s*\)\s"),
    re.compile(r"^\s*(I{1,3}V?|VI{0,3}|IX|XI{0,3})\.\s+\w"),
    re.compile(r"^\s*(WHEREAS|NOW\s+THEREFORE|RECITALS?)\b", re.IGNORECASE),
]


def _is_clause(text: str) -> bool:
    return any(p.search(text) for p in _CLAUSE_PATTERNS)


def chunk(result: ParseResult) -> list[StructuralChunk]:
    doc = result.doc
    out: list[StructuralChunk] = []
    heading_path: list[str] = []
    parent_id: str | None = None
    prose_buf: list[tuple] = []
    list_buf: list[tuple] = []
    counter = 0
    last_caption = ""

    def flush_prose():
        nonlocal counter
        if not prose_buf:
            return
        combined = "\n".join(
            getattr(it, "text", "") or "" for it, _ in prose_buf
        ).strip()
        if not combined:
            prose_buf.clear()
            return
        hp = prose_buf[0][1]
        items = [it for it, _ in prose_buf]
        for seg in _split_by_tokens(combined, CHUNK_MAX_TOKENS):
            out.append(StructuralChunk(
                chunk_id=str(uuid.uuid4()), chunk_type="prose", is_leaf=True,
                text=seg, context_text=_make_context(hp, seg),
                parent_id=parent_id, heading_path=list(hp), doc_items=items,
                chunk_index_in_parent=counter,
            ))
            counter += 1
        prose_buf.clear()

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
            flush_prose()
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
            flush_prose()
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
            flush_prose()
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
            flush_prose()
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
            if text.strip() and _is_clause(text):
                flush_prose()
                flush_list()
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type="clause", is_leaf=True,
                    text=text, context_text=_make_context(heading_path, text),
                    parent_id=parent_id, heading_path=list(heading_path),
                    doc_items=[item], chunk_index_in_parent=counter,
                ))
                counter += 1
            elif text.strip():
                list_buf.append((item, list(heading_path)))

        elif label in (DocItemLabel.TEXT, DocItemLabel.PARAGRAPH) and text.strip():
            flush_list()
            if _is_clause(text):
                flush_prose()
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type="clause", is_leaf=True,
                    text=text, context_text=_make_context(heading_path, text),
                    parent_id=parent_id, heading_path=list(heading_path),
                    doc_items=[item], chunk_index_in_parent=counter,
                ))
                counter += 1
            else:
                prose_buf.append((item, list(heading_path)))

        elif text.strip():
            flush_list()
            prose_buf.append((item, list(heading_path)))

    flush_prose()
    flush_list()
    return out
