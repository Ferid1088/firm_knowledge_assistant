"""TableAtomic chunker — B: table_structured.

Extracts EVERY table from the Docling document as an atomic leaf chunk.
Prose between tables is preserved as windowed prose leaves (not dropped).
Figures, formulas, and lists are handled as atomic leaves.
"""
from __future__ import annotations
import uuid
from docling_core.types.doc import DocItemLabel

from backend.tools.chunk import (
    StructuralChunk, extract_table_structure, _make_context,
    _heading_path_str, _split_by_tokens, _looks_like_recommendation,
    _HEADING_LABELS, _PROSE_LABELS, _PICTURE_LABELS, _CAPTION_LABELS,
    _FORMULA_LABELS, _CODE_LABELS, _FOOTNOTE_LABELS,
    CHUNK_MAX_TOKENS,
)
from backend.tools.parsers.parse_result import ParseResult


def chunk(result: ParseResult) -> list[StructuralChunk]:
    """Extract every table as an atomic leaf; prose is token-windowed, not dropped."""
    doc = result.doc
    out: list[StructuralChunk] = []
    heading_path: list[str] = []
    parent_id: str | None = None
    prose_buf: list[tuple] = []
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

    try:
        items = list(doc.iterate_items())
    except Exception:
        return out

    for item, level in items:
        label = getattr(item, "label", None)
        text = getattr(item, "text", "") or ""

        if label in _HEADING_LABELS:
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
            if text.strip():
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type="formula", is_leaf=True,
                    text=text, context_text=_make_context(heading_path, text),
                    parent_id=parent_id, heading_path=list(heading_path),
                    doc_items=[item], chunk_index_in_parent=counter,
                ))
                counter += 1

        elif text.strip():
            prose_buf.append((item, list(heading_path)))

    flush_prose()
    return out
