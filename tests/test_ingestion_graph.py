"""Tests for the ingestion graph structure and triage routing."""
import pytest


def test_ingestion_graph_builds():
    from backend.graph.ingestion_graph import build_ingestion_graph
    graph = build_ingestion_graph()
    assert graph is not None


def test_triage_text_pdf(tmp_path):
    """A PDF with text should route to text_parse."""
    from backend.graph.ingestion_graph import triage_node
    # Create a minimal PDF with text using fitz
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello world " * 20)
    pdf_path = str(tmp_path / "text.pdf")
    doc.save(pdf_path)
    doc.close()

    state = {"source_path": pdf_path}
    out = triage_node(state)
    assert out["is_scanned"] is False
    assert out["is_image"] is False


def test_triage_image_file():
    from backend.graph.ingestion_graph import triage_node
    state = {"source_path": "photo.jpg"}
    out = triage_node(state)
    assert out["is_scanned"] is True
    assert out["is_image"] is True


def test_triage_docx():
    from backend.graph.ingestion_graph import triage_node
    state = {"source_path": "report.docx"}
    out = triage_node(state)
    assert out["is_scanned"] is False
    assert out["is_image"] is False


def test_route_after_triage():
    from backend.graph.ingestion_graph import _route_after_triage
    assert _route_after_triage({"is_scanned": True}) == "ocr"
    assert _route_after_triage({"is_scanned": False}) == "text"
