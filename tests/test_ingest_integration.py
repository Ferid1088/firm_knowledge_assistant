"""Integration test: pipeline.ingest() now calls the ingestion graph."""
import pytest


def test_ingest_result_type():
    """pipeline.ingest() should still return an IngestResult."""
    from dataclasses import fields
    from backend.tools.pipeline import IngestResult
    field_names = {f.name for f in fields(IngestResult)}
    assert "n_chunks" in field_names
    assert "doc_type" in field_names
    assert "is_scanned" in field_names


def test_graph_produces_ingest_result_fields():
    """The graph's run_ingest output has the fields we need for IngestResult."""
    from backend.graph.ingestion.state import IngestionState
    import typing
    hints = typing.get_type_hints(IngestionState)
    assert "n_chunks" in hints
    assert "resolved_type" in hints
    assert "is_scanned_result" in hints


def test_ingest_delegates_to_graph(monkeypatch):
    """pipeline.ingest() should call run_ingest from the graph module."""
    call_log = []

    def fake_run_ingest(**kwargs):
        call_log.append(kwargs)
        return {
            "n_chunks": 42,
            "resolved_type": "generic",
            "type_confidence": 0.95,
            "is_scanned_result": False,
            "empty_pages": [],
            "parser_name": "docling",
            "chunker_name": "structural",
        }

    monkeypatch.setattr(
        "backend.graph.ingestion.run_ingest", fake_run_ingest
    )
    from backend.tools.pipeline import ingest, IngestResult
    result = ingest("/tmp/fake.pdf", verbose=False)

    assert isinstance(result, IngestResult)
    assert result.n_chunks == 42
    assert result.doc_type == "generic"
    assert result.is_scanned is False
    assert len(call_log) == 1
    assert call_log[0]["source_path"] == "/tmp/fake.pdf"


def test_ingest_raises_on_graph_error(monkeypatch):
    """pipeline.ingest() should raise RuntimeError when the graph sets error."""
    def fake_run_ingest(**kwargs):
        return {"error": "Parser failed: corrupt file"}

    monkeypatch.setattr(
        "backend.graph.ingestion.run_ingest", fake_run_ingest
    )
    from backend.tools.pipeline import ingest
    with pytest.raises(RuntimeError, match="Parser failed"):
        ingest("/tmp/fake.pdf", verbose=False)


def test_kept_helpers_importable():
    """Helpers that graph nodes import must remain in pipeline.py."""
    from backend.tools.pipeline import (
        _detect_lang,
        _enrich_embed_texts,
        _get_reader,
        IngestResult,
        rebuild_bm25_indices,
    )
    assert callable(_detect_lang)
    assert callable(_enrich_embed_texts)
    assert callable(_get_reader)
    assert callable(rebuild_bm25_indices)
