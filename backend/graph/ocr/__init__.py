"""OCR sub-package — scanned document processing subgraph."""
from backend.graph.ocr.state import OCRState
from backend.graph.ocr.graph import build_ocr_subgraph

__all__ = ["build_ocr_subgraph", "OCRState"]
