"""GET /api/originals/{doc_id} — serve source PDFs from internal store."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.config import ORIGINALS_DIR

router = APIRouter()


@router.get("/originals/{doc_id}")
def get_original(doc_id: str):
    safe_name = Path(doc_id).name
    pdf_path = Path(ORIGINALS_DIR) / f"{safe_name}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="document not found")
    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path.name)
