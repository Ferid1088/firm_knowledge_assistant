"""Structural parent-child chunker.

Division of labor:
  heading       -> parent node (is_leaf=False); carries heading path for children
  table         -> atomic leaf (chunk_type=table), kept WHOLE
  recommendation/clause -> atomic leaf (chunk_type=recommendation), kept WHOLE
  prose         -> leaves produced by HybridChunker (token-aware, within section only)

HybridChunker is ONLY used for prose windowing. It does NOT touch atomic leaves.
"""
from __future__ import annotations
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc import DocItemLabel
from transformers import AutoTokenizer

from config import EMBED_MODEL_ID, CHUNK_MAX_TOKENS


# ── Recommendation / clause detection heuristics ──────────────────────────
# Adjust patterns for the document family. Falls back to prose if no match.
_REC_PATTERNS = [
    re.compile(r"^\s*§\s*\d+", re.MULTILINE),           # §1, § 23
    re.compile(r"^\s*Artikel\s+\d+", re.MULTILINE),      # Artikel 5
    re.compile(r"^\s*Absatz\s+\d+", re.MULTILINE),       # Absatz 2
    re.compile(r"^\s*\(\d+\)\s"),                         # (1) ...
    re.compile(r"^\s*[A-Z]\.\s+\d+"),                    # A. 1
]


def _looks_like_recommendation(text: str) -> bool:
    return any(p.search(text) for p in _REC_PATTERNS)


# ── Chunk dataclass ────────────────────────────────────────────────────────

@dataclass
class StructuralChunk:
    chunk_id: str
    chunk_type: str           # "table" | "recommendation" | "prose" | "heading"
    is_leaf: bool
    text: str
    context_text: str         # heading path + text (what gets embedded)
    parent_id: Optional[str]
    heading_path: list[str]   # e.g. ["§ 14", "Absatz 2"]
    doc_items: list           # original Docling doc_items for bbox extraction
    chunk_index_in_parent: int = 0
    metadata: dict = field(default_factory=dict)


# ── Chunker ────────────────────────────────────────────────────────────────

def make_prose_chunker(model_id: str = EMBED_MODEL_ID, max_tokens: int = CHUNK_MAX_TOKENS):
    tokenizer = HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(model_id),
        max_tokens=max_tokens,
    )
    return HybridChunker(tokenizer=tokenizer, merge_peers=True)


def _heading_path_str(path: list[str]) -> str:
    return " > ".join(path) if path else ""


def chunk_document(doc, prose_chunker=None) -> list[StructuralChunk]:
    """
    Walk the Docling document tree and produce StructuralChunks.
    Tables and recommendations are atomic leaves.
    Prose is windowed by HybridChunker within each section.
    """
    if prose_chunker is None:
        prose_chunker = make_prose_chunker()

    chunks: list[StructuralChunk] = []
    _walk(doc, prose_chunker, [], None, chunks, [0])
    return chunks


def _walk(doc, prose_chunker, heading_path: list[str], parent_id: Optional[str],
          out: list[StructuralChunk], counter: list[int]):
    """Recursively walk items using the Docling document's body children."""
    try:
        items = list(doc.iterate_items())
    except Exception:
        return

    prose_buffer: list = []
    prose_heading_path: list[str] = list(heading_path)

    def _flush_prose():
        if not prose_buffer:
            return
        # Create a minimal fake document slice for HybridChunker
        # We pass each prose item through contextualize individually
        for item, item_heading_path in prose_buffer:
            text = item.text if hasattr(item, "text") else str(item)
            if not text.strip():
                continue
            ctx = _heading_path_str(item_heading_path)
            context_text = f"{ctx}\n\n{text}".strip() if ctx else text
            cid = str(uuid.uuid4())
            out.append(StructuralChunk(
                chunk_id=cid,
                chunk_type="prose",
                is_leaf=True,
                text=text,
                context_text=context_text,
                parent_id=parent_id,
                heading_path=list(item_heading_path),
                doc_items=[item],
                chunk_index_in_parent=counter[0],
            ))
            counter[0] += 1
        prose_buffer.clear()

    for item, level in items:
        label = getattr(item, "label", None)
        text = getattr(item, "text", "") or ""

        if label == DocItemLabel.SECTION_HEADER or label == DocItemLabel.TITLE:
            _flush_prose()
            heading_path = list(heading_path)
            # Trim heading stack to current level
            if level is not None and isinstance(level, int):
                heading_path = heading_path[:max(0, level - 1)]
            heading_path.append(text.strip())
            prose_heading_path = list(heading_path)
            # Heading node (not a leaf, just anchors the path)
            cid = str(uuid.uuid4())
            out.append(StructuralChunk(
                chunk_id=cid,
                chunk_type="heading",
                is_leaf=False,
                text=text,
                context_text=text,
                parent_id=parent_id,
                heading_path=list(heading_path),
                doc_items=[item],
                chunk_index_in_parent=counter[0],
            ))
            counter[0] += 1
            parent_id = cid

        elif label == DocItemLabel.TABLE:
            _flush_prose()
            try:
                text = item.export_to_markdown(doc=doc)
            except Exception:
                text = text or ""
            if not text.strip():
                continue
            cid = str(uuid.uuid4())
            ctx = _heading_path_str(prose_heading_path)
            context_text = f"{ctx}\n\n{text}".strip() if ctx else text
            out.append(StructuralChunk(
                chunk_id=cid,
                chunk_type="table",
                is_leaf=True,
                text=text,
                context_text=context_text,
                parent_id=parent_id,
                heading_path=list(prose_heading_path),
                doc_items=[item],
                chunk_index_in_parent=counter[0],
            ))
            counter[0] += 1

        elif label in (DocItemLabel.TEXT, DocItemLabel.PARAGRAPH, DocItemLabel.LIST_ITEM):
            if text.strip() and _looks_like_recommendation(text):
                _flush_prose()
                cid = str(uuid.uuid4())
                ctx = _heading_path_str(prose_heading_path)
                context_text = f"{ctx}\n\n{text}".strip() if ctx else text
                out.append(StructuralChunk(
                    chunk_id=cid,
                    chunk_type="recommendation",
                    is_leaf=True,
                    text=text,
                    context_text=context_text,
                    parent_id=parent_id,
                    heading_path=list(prose_heading_path),
                    doc_items=[item],
                    chunk_index_in_parent=counter[0],
                ))
                counter[0] += 1
            else:
                prose_buffer.append((item, list(prose_heading_path)))

        # other labels (figure captions, footnotes, etc.) go to prose
        elif text.strip():
            prose_buffer.append((item, list(prose_heading_path)))

    _flush_prose()
