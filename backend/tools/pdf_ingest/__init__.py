"""PDF ingest tool — exposes the two public entry points."""
from backend.tools.pdf_ingest.pipeline import ingest, rebuild_bm25_indices

__all__ = ["ingest", "rebuild_bm25_indices"]
