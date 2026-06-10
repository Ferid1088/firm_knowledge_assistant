"""Build normalized bbox addresses from StructuralChunk doc_items."""
from __future__ import annotations
import pypdfium2 as pdfium


def page_sizes(pdf_path: str) -> dict[int, tuple[float, float]]:
    """Return {1-based-page: (width_pts, height_pts)}."""
    pdf = pdfium.PdfDocument(pdf_path)
    sizes = {i + 1: pdf[i].get_size() for i in range(len(pdf))}
    pdf.close()
    return sizes


def chunk_address(chunk, doc_id: str, sizes: dict[int, tuple[float, float]]) -> dict:
    """
    Normalize bboxes to top-left fractions 0..1.
    Works with StructuralChunk (doc_items list) or old-style HybridChunker chunks.
    """
    boxes: dict[int, list[list[float]]] = {}

    doc_items = getattr(chunk, "doc_items", None) or []
    # Also handle old HybridChunker chunks via chunk.meta.doc_items
    if not doc_items:
        doc_items = getattr(getattr(chunk, "meta", None), "doc_items", None) or []

    for item in doc_items:
        for prov in getattr(item, "prov", []) or []:
            page_no = prov.page_no
            if page_no not in sizes:
                continue
            w, h = sizes[page_no]
            b = prov.bbox.to_top_left_origin(h)
            boxes.setdefault(page_no, []).append([b.l / w, b.t / h, b.r / w, b.b / h])

    heading_path = getattr(chunk, "heading_path", None) or []

    return {
        "doc_id": doc_id,
        "page": min(boxes) if boxes else None,
        "heading_path": heading_path,
        "boxes": boxes,
    }
