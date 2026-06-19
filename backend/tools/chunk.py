"""Structural parent-child chunker — production-grade.

Division of labor:
  heading           -> parent node (is_leaf=False); carries heading path for children
  table             -> atomic leaf (chunk_type=table), kept WHOLE
  recommendation    -> atomic leaf (chunk_type=recommendation), kept WHOLE
  list              -> atomic leaf (chunk_type=list), contiguous LIST_ITEMs grouped
  picture/figure    -> atomic leaf (chunk_type=figure), with caption metadata
  formula           -> atomic leaf (chunk_type=formula), kept whole
  code              -> atomic leaf (chunk_type=code), kept whole
  caption           -> attached to preceding figure/table as metadata
  footnote          -> atomic leaf (chunk_type=footnote)
  prose             -> TOKEN-WINDOWED leaves via _split_by_tokens (max CHUNK_MAX_TOKENS)
"""
from __future__ import annotations
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

from docling_core.types.doc import DocItemLabel
from transformers import AutoTokenizer

from backend.config import EMBED_MODEL_ID, CHUNK_MAX_TOKENS


# ── Tokenizer singleton for token counting + splitting ────────────────────

_tokenizer = None


def _get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = AutoTokenizer.from_pretrained(EMBED_MODEL_ID)
    return _tokenizer


def token_len(text: str) -> int:
    return len(_get_tokenizer().encode(text, add_special_tokens=False))


def _batch_token_lens(texts: list[str]) -> list[int]:
    """Tokenize all texts in one call and return per-text token counts."""
    if not texts:
        return []
    tok = _get_tokenizer()
    encoded = tok(texts, add_special_tokens=False, return_attention_mask=False)
    return [len(ids) for ids in encoded["input_ids"]]


def _split_by_tokens(text: str, max_tokens: int = CHUNK_MAX_TOKENS) -> list[str]:
    """Split text into segments of at most max_tokens, breaking at sentence/paragraph boundaries.

    Uses batch tokenization to avoid O(n²) tokenizer calls on large texts.
    """
    if token_len(text) <= max_tokens:
        return [text]

    paragraphs = text.split("\n")
    para_lens = _batch_token_lens(paragraphs)

    segments: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for para, para_tokens in zip(paragraphs, para_lens):
        if para_tokens > max_tokens:
            if current:
                segments.append("\n".join(current))
                current = []
                current_tokens = 0
            sentences = re.split(r'(?<=[.!?])\s+', para)
            sent_lens = _batch_token_lens(sentences)
            for sent, sent_tokens in zip(sentences, sent_lens):
                if current_tokens + sent_tokens > max_tokens and current:
                    segments.append("\n".join(current))
                    current = []
                    current_tokens = 0
                current.append(sent)
                current_tokens += sent_tokens
        elif current_tokens + para_tokens > max_tokens and current:
            segments.append("\n".join(current))
            current = [para]
            current_tokens = para_tokens
        else:
            current.append(para)
            current_tokens += para_tokens

    if current:
        segments.append("\n".join(current))

    return [s for s in segments if s.strip()]


# ── Recommendation / clause detection heuristics ──────────────────────────

_REC_PATTERNS = [
    re.compile(r"^\s*§\s*\d+", re.MULTILINE),
    re.compile(r"^\s*Artikel\s+\d+", re.MULTILINE),
    re.compile(r"^\s*Absatz\s+\d+", re.MULTILINE),
    re.compile(r"^\s*\(\d+\)\s"),
    re.compile(r"^\s*[A-Z]\.\s+\d+"),
]


def _looks_like_recommendation(text: str) -> bool:
    return any(p.search(text) for p in _REC_PATTERNS)


# ── Table structure helpers ───────────────────────────────────────────────


def extract_table_structure(item) -> dict:
    """Extract structured metadata from a Docling TableItem."""
    try:
        grid = item.data.grid
        n_rows = item.data.num_rows
        n_cols = item.data.num_cols
    except Exception:
        return {}
    headers: list[str] = []
    rows: list[list[str]] = []
    for row in grid:
        row_cells: list[str] = []
        for cell in row:
            cell_text = getattr(cell, "text", "") or ""
            row_cells.append(cell_text)
            label = getattr(cell, "label", "")
            if label in ("col_header", "row_header") and cell_text:
                if cell_text not in headers:
                    headers.append(cell_text)
        rows.append(row_cells)
    return {"n_rows": n_rows, "n_cols": n_cols, "headers": headers, "rows": rows}


def classify_table_role(headers: list[str], schemas: dict) -> str:
    if not schemas or not headers:
        return "data_table"
    header_lower = " ".join(h.lower() for h in headers)
    for role, keywords in schemas.items():
        if any(kw in header_lower for kw in keywords):
            return role
    return "data_table"


# ── Chunk dataclass ───────────────────────────────────────────────────────

@dataclass
class StructuralChunk:
    """Single retrieval unit produced by the structural chunker."""

    chunk_id: str
    chunk_type: str           # table|recommendation|prose|heading|list|figure|formula|code|footnote
    is_leaf: bool
    text: str
    context_text: str         # heading path + text (what gets embedded)
    parent_id: Optional[str]
    heading_path: list[str]
    doc_items: list
    chunk_index_in_parent: int = 0
    metadata: dict = field(default_factory=dict)


# ── Helpers ───────────────────────────────────────────────────────────────

def _heading_path_str(path: list[str]) -> str:
    return " > ".join(path) if path else ""


def _make_context(heading_path: list[str], text: str) -> str:
    ctx = _heading_path_str(heading_path)
    return f"{ctx}\n\n{text}".strip() if ctx else text


# ── DocItemLabel sets ─────────────────────────────────────────────────────

_HEADING_LABELS = {DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE}
_PROSE_LABELS = {DocItemLabel.TEXT, DocItemLabel.PARAGRAPH}

_PICTURE_LABELS = set()
_CAPTION_LABELS = set()
_FORMULA_LABELS = set()
_CODE_LABELS = set()
_FOOTNOTE_LABELS = set()

for _name in ("PICTURE", "FIGURE"):
    if hasattr(DocItemLabel, _name):
        _PICTURE_LABELS.add(getattr(DocItemLabel, _name))
for _name in ("CAPTION",):
    if hasattr(DocItemLabel, _name):
        _CAPTION_LABELS.add(getattr(DocItemLabel, _name))
for _name in ("FORMULA", "EQUATION"):
    if hasattr(DocItemLabel, _name):
        _FORMULA_LABELS.add(getattr(DocItemLabel, _name))
for _name in ("CODE",):
    if hasattr(DocItemLabel, _name):
        _CODE_LABELS.add(getattr(DocItemLabel, _name))
for _name in ("FOOTNOTE",):
    if hasattr(DocItemLabel, _name):
        _FOOTNOTE_LABELS.add(getattr(DocItemLabel, _name))


# ── Main chunker ──────────────────────────────────────────────────────────

def chunk_document(doc) -> list[StructuralChunk]:
    """Walk the Docling document tree and produce StructuralChunks.

    Tables, figures, formulas, and recommendations are atomic leaves.
    Lists are grouped contiguously. Prose is token-windowed.
    """
    chunks: list[StructuralChunk] = []
    _walk(doc, [], None, chunks, [0])
    return chunks


def _walk(doc, heading_path: list[str], parent_id: Optional[str],
          out: list[StructuralChunk], counter: list[int]):
    try:
        items = list(doc.iterate_items())
    except Exception:
        return

    prose_buffer: list = []
    list_buffer: list = []
    current_heading_path: list[str] = list(heading_path)
    last_caption: str = ""

    def _flush_list():
        if not list_buffer:
            return
        texts = []
        doc_items = []
        for li_item, li_hp in list_buffer:
            t = getattr(li_item, "text", "") or ""
            if t.strip():
                texts.append(f"• {t.strip()}")
                doc_items.append(li_item)
        if not texts:
            list_buffer.clear()
            return
        text = "\n".join(texts)
        hp = list_buffer[0][1]
        out.append(StructuralChunk(
            chunk_id=str(uuid.uuid4()), chunk_type="list", is_leaf=True,
            text=text, context_text=_make_context(hp, text),
            parent_id=parent_id, heading_path=list(hp), doc_items=doc_items,
            chunk_index_in_parent=counter[0],
        ))
        counter[0] += 1
        list_buffer.clear()

    def _flush_prose():
        if not prose_buffer:
            return
        combined_texts: list[tuple[str, list[str], list]] = []
        current_text_parts: list[str] = []
        current_hp = prose_buffer[0][1]
        current_items: list = []

        for item, item_hp in prose_buffer:
            t = getattr(item, "text", "") if hasattr(item, "text") else str(item)
            if not t.strip():
                continue
            if item_hp != current_hp and current_text_parts:
                combined_texts.append(("\n".join(current_text_parts), current_hp, current_items))
                current_text_parts = []
                current_items = []
                current_hp = item_hp
            current_text_parts.append(t)
            current_items.append(item)

        if current_text_parts:
            combined_texts.append(("\n".join(current_text_parts), current_hp, current_items))

        for combined, hp, doc_items in combined_texts:
            segments = _split_by_tokens(combined, CHUNK_MAX_TOKENS)
            for seg in segments:
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type="prose", is_leaf=True,
                    text=seg, context_text=_make_context(hp, seg),
                    parent_id=parent_id, heading_path=list(hp), doc_items=doc_items,
                    chunk_index_in_parent=counter[0],
                ))
                counter[0] += 1
        prose_buffer.clear()

    for item, level in items:
        label = getattr(item, "label", None)
        text = getattr(item, "text", "") or ""

        # ── Headings ──────────────────────────────────────────────────
        if label in _HEADING_LABELS:
            _flush_prose()
            _flush_list()
            current_heading_path = list(current_heading_path)
            if level is not None and isinstance(level, int):
                current_heading_path = current_heading_path[:max(0, level - 1)]
            current_heading_path.append(text.strip())
            cid = str(uuid.uuid4())
            out.append(StructuralChunk(
                chunk_id=cid, chunk_type="heading", is_leaf=False,
                text=text, context_text=text,
                parent_id=parent_id, heading_path=list(current_heading_path),
                doc_items=[item], chunk_index_in_parent=counter[0],
            ))
            counter[0] += 1
            parent_id = cid

        # ── Tables ────────────────────────────────────────────────────
        elif label == DocItemLabel.TABLE:
            _flush_prose()
            _flush_list()
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
                text=md, context_text=_make_context(current_heading_path, md),
                parent_id=parent_id, heading_path=list(current_heading_path),
                doc_items=[item], chunk_index_in_parent=counter[0],
                metadata=meta,
            ))
            counter[0] += 1

        # ── Pictures / Figures ────────────────────────────────────────
        elif _PICTURE_LABELS and label in _PICTURE_LABELS:
            _flush_prose()
            _flush_list()
            caption = last_caption or text or ""
            last_caption = ""
            fig_text = f"[Figure: {caption}]" if caption else "[Figure]"
            out.append(StructuralChunk(
                chunk_id=str(uuid.uuid4()), chunk_type="figure", is_leaf=True,
                text=fig_text,
                context_text=_make_context(current_heading_path, fig_text),
                parent_id=parent_id, heading_path=list(current_heading_path),
                doc_items=[item], chunk_index_in_parent=counter[0],
                metadata={"caption": caption, "needs_description": True},
            ))
            counter[0] += 1

        # ── Captions ──────────────────────────────────────────────────
        elif _CAPTION_LABELS and label in _CAPTION_LABELS:
            last_caption = text.strip()
            if out and out[-1].chunk_type in ("figure", "table"):
                out[-1].metadata["caption"] = last_caption
                cap_ctx = f"{out[-1].text}\nCaption: {last_caption}"
                out[-1].context_text = _make_context(current_heading_path, cap_ctx)
                last_caption = ""

        # ── Formulas ──────────────────────────────────────────────────
        elif _FORMULA_LABELS and label in _FORMULA_LABELS:
            _flush_prose()
            _flush_list()
            if text.strip():
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type="formula", is_leaf=True,
                    text=text, context_text=_make_context(current_heading_path, text),
                    parent_id=parent_id, heading_path=list(current_heading_path),
                    doc_items=[item], chunk_index_in_parent=counter[0],
                ))
                counter[0] += 1

        # ── Code blocks ───────────────────────────────────────────────
        elif _CODE_LABELS and label in _CODE_LABELS:
            _flush_prose()
            _flush_list()
            if text.strip():
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type="code", is_leaf=True,
                    text=text, context_text=_make_context(current_heading_path, text),
                    parent_id=parent_id, heading_path=list(current_heading_path),
                    doc_items=[item], chunk_index_in_parent=counter[0],
                ))
                counter[0] += 1

        # ── Footnotes ─────────────────────────────────────────────────
        elif _FOOTNOTE_LABELS and label in _FOOTNOTE_LABELS:
            _flush_prose()
            _flush_list()
            if text.strip():
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type="footnote", is_leaf=True,
                    text=text, context_text=_make_context(current_heading_path, text),
                    parent_id=parent_id, heading_path=list(current_heading_path),
                    doc_items=[item], chunk_index_in_parent=counter[0],
                ))
                counter[0] += 1

        # ── List items ────────────────────────────────────────────────
        elif label == DocItemLabel.LIST_ITEM:
            if text.strip() and _looks_like_recommendation(text):
                _flush_prose()
                _flush_list()
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type="recommendation",
                    is_leaf=True, text=text,
                    context_text=_make_context(current_heading_path, text),
                    parent_id=parent_id, heading_path=list(current_heading_path),
                    doc_items=[item], chunk_index_in_parent=counter[0],
                ))
                counter[0] += 1
            elif text.strip():
                list_buffer.append((item, list(current_heading_path)))

        # ── Prose (TEXT / PARAGRAPH) ──────────────────────────────────
        elif label in _PROSE_LABELS:
            _flush_list()
            if text.strip() and _looks_like_recommendation(text):
                _flush_prose()
                out.append(StructuralChunk(
                    chunk_id=str(uuid.uuid4()), chunk_type="recommendation",
                    is_leaf=True, text=text,
                    context_text=_make_context(current_heading_path, text),
                    parent_id=parent_id, heading_path=list(current_heading_path),
                    doc_items=[item], chunk_index_in_parent=counter[0],
                ))
                counter[0] += 1
            elif text.strip():
                prose_buffer.append((item, list(current_heading_path)))

        # ── Any other labeled element with text ───────────────────────
        elif text.strip():
            _flush_list()
            prose_buffer.append((item, list(current_heading_path)))

    _flush_list()
    _flush_prose()
