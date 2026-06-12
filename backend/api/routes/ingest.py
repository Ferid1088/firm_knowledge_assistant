"""POST /api/ingest  +  GET /api/ingest/{job_id}"""
from __future__ import annotations
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.config import ORIGINALS_DIR

router = APIRouter()

_ingest_lock = threading.Lock()


class IngestJobStatus(BaseModel):
    job_id: str
    status: str
    doc_id: str
    n_chunks: Optional[int] = None
    error: Optional[str] = None


_ingest_jobs: dict[str, IngestJobStatus] = {}


def _run_ingest_job(job_id: str, tmp_path: Path) -> None:
    from backend.tools.pdf_ingest import ingest, rebuild_bm25_indices
    from backend.services.model_registry import set_bm25_indices

    job = _ingest_jobs[job_id]
    job.status = "running"
    try:
        with _ingest_lock:
            n = ingest(str(tmp_path))
            set_bm25_indices(rebuild_bm25_indices())
        job.n_chunks = n
        job.status = "done"
    except Exception as e:
        job.status = "error"
        job.error = str(e)
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/ingest", response_model=IngestJobStatus)
def ingest_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf files are accepted")
    doc_id = re.sub(r"[^A-Za-z0-9_-]", "_", Path(file.filename).stem) or "doc"
    staging_dir = Path(ORIGINALS_DIR) / "_staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = staging_dir / f"{doc_id}.pdf"
    with tmp_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    job_id = uuid.uuid4().hex
    _ingest_jobs[job_id] = IngestJobStatus(job_id=job_id, status="queued", doc_id=doc_id)
    background_tasks.add_task(_run_ingest_job, job_id, tmp_path)
    return _ingest_jobs[job_id]


@router.get("/ingest/{job_id}", response_model=IngestJobStatus)
def get_ingest_status(job_id: str):
    job = _ingest_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="ingest job not found")
    return job
