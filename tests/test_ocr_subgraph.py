"""Tests for the OCR subgraph structure and routing logic."""
import pytest


def test_ocr_subgraph_builds():
    from backend.graph.ocr_subgraph import build_ocr_subgraph
    graph = build_ocr_subgraph()
    assert graph is not None


def test_route_after_ocr_done():
    from backend.graph.ocr_subgraph import _route_after_ocr
    state = {"attempt": 1, "low_confidence_pages": [], "needs_review": False}
    assert _route_after_ocr(state) == "done"


def test_route_after_ocr_retry():
    from backend.graph.ocr_subgraph import _route_after_ocr
    state = {"attempt": 1, "low_confidence_pages": [1, 2, 3], "total_pages": 5, "needs_review": False}
    assert _route_after_ocr(state) == "retry"


def test_route_after_ocr_give_up_max_attempts():
    from backend.graph.ocr_subgraph import _route_after_ocr
    state = {"attempt": 2, "low_confidence_pages": [1], "total_pages": 10, "needs_review": False}
    assert _route_after_ocr(state) == "give_up"


def test_route_after_ocr_give_up_not_worthwhile():
    """1 bad page out of 80 — not worth a re-run."""
    from backend.graph.ocr_subgraph import _route_after_ocr
    state = {"attempt": 1, "low_confidence_pages": [5], "total_pages": 80, "needs_review": False}
    assert _route_after_ocr(state) == "give_up"


def test_escalate_switches_engine():
    from backend.graph.ocr_subgraph import escalate_node
    state = {"engine": "easyocr", "images_scale": 2.0}
    out = escalate_node(state)
    assert out["engine"] == "tesseract"
    assert out["images_scale"] == 3.0  # 2.0 * 1.5


def test_flag_for_review():
    from backend.graph.ocr_subgraph import flag_for_review_node
    state = {"source_path": "test.pdf", "low_confidence_pages": [1], "total_pages": 5, "attempt": 2}
    out = flag_for_review_node(state)
    assert out["needs_review"] is True
