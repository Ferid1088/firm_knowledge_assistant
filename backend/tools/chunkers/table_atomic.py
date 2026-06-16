"""TableAtomic chunker — B: table_structured.

Extracts EVERY table from the Docling document as an atomic leaf chunk.
Non-table content (prose headings) becomes parent nodes to preserve address
context. Designed for documents whose primary content is tabular data.

Embed strategy (step 8): for tables larger than OVERSIZE_EMBED_THRESHOLD tokens,
the pipeline generates a contextual description and embeds that instead — the
full table is always stored and returned.
"""
from __future__ import annotations
import uuid
from docling_core.types.doc import DocItemLabel

from backend.tools.chunk import StructuralChunk
from backend.tools.parsers.parse_result import ParseResult


def _heading_path_str(path: list[str]) -> str:
    return " > ".join(path) if path else ""


def chunk(result: ParseResult) -> list[StructuralChunk]:
    doc = result.doc
    out: list[StructuralChunk] = []
    heading_path: list[str] = []
    parent_id: str | None = None
    counter = 0

    try:
        items = list(doc.iterate_items())
    except Exception:
        return out

    for item, level in items:
        label = getattr(item, "label", None)
        text = getattr(item, "text", "") or ""

        if label in (DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE):
            # Trim path to current heading level
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

        # Prose items become inline notes attached to the last heading (not leaf chunks)
        # so that table context remains clean.

    return out
