"""End-to-end: ingest a real PDF through the graph pipeline."""
import pytest
from pathlib import Path

SAMPLE_DIR = Path("raw_knowlegebase")


@pytest.mark.skipif(
    not SAMPLE_DIR.exists() or not list(SAMPLE_DIR.glob("*.pdf")),
    reason="No sample PDFs found in raw_knowlegebase/",
)
def test_ingest_real_pdf():
    from backend.tools.pipeline import ingest

    pdf = next(SAMPLE_DIR.glob("*.pdf"))
    result = ingest(str(pdf), verbose=True)

    assert result.n_chunks > 0
    assert result.doc_type is not None
    assert result.parser_name is not None
    print(f"\nOK: {pdf.name} -> {result.n_chunks} chunks, type={result.doc_type}, "
          f"parser={result.parser_name}, chunker={result.chunker_name}")
