"""FastAPI backend for the Next.js + assistant-ui frontend.

Backend is frontend-agnostic: this module is the API; the UI is a thin layer
over artifact_chunks (CLAUDE.md architecture principle). The LangGraph engine
(src/query/graph/graph.py) does all orchestration; this file adapts HTTP <-> graph
for queries, and HTTP <-> src/ingest/pipeline.py for document ingestion.

Air-gap: CORS restricted to the local Next.js dev origin; offline/telemetry
flags are set in config.py (imported on module load).
"""
from __future__ import annotations

import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import ORIGINALS_DIR, AVAILABLE_LANGUAGES, OLLAMA_MODEL, RETRIEVE_K

app = FastAPI(title="Local RAG API")

# Pilot: Next.js dev server runs on localhost:3000. Internal-only origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_bm25_loaded = False
# Serializes ingestion jobs: BM25 rebuild + Qdrant writes are not safe to
# interleave across concurrent /api/ingest calls.
_ingest_lock = threading.Lock()


def _refresh_bm25_indices() -> None:
    from src.ingest.pipeline import rebuild_bm25_indices
    from src.query.graph.nodes import set_bm25_indices

    set_bm25_indices(rebuild_bm25_indices())


def _ensure_bm25_loaded() -> None:
    """BM25 indices are not persisted with Qdrant; rebuild once per process."""
    global _bm25_loaded
    if _bm25_loaded:
        return
    _refresh_bm25_indices()
    _bm25_loaded = True


class ChatRequest(BaseModel):
    question: str
    active_lang_codes: Optional[list[str]] = None


class ChatResponse(BaseModel):
    answer: str
    answer_lang: str
    confidence: float
    attempts: int
    claims: list[dict]
    artifact_chunks: list[dict]


class IngestJobStatus(BaseModel):
    job_id: str
    status: str  # "queued" | "running" | "done" | "error"
    doc_id: str
    n_chunks: Optional[int] = None
    error: Optional[str] = None


# In-memory job tracking (pilot scope; one process). Keyed by job_id.
_ingest_jobs: dict[str, IngestJobStatus] = {}


@app.get("/api/config")
def get_config():
    """Expose UI-relevant config: available languages, model id, top-k."""
    return {
        "available_languages": [code for code, *_ in AVAILABLE_LANGUAGES],
        "default_active_languages": [code for code, *_ in AVAILABLE_LANGUAGES],
        "ollama_model": OLLAMA_MODEL,
        "top_k": RETRIEVE_K,
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    from src.query.graph.graph import run as graph_run

    _ensure_bm25_loaded()

    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    state = graph_run(req.question, active_lang_codes=req.active_lang_codes or ["de"])

    return ChatResponse(
        answer=state.get("answer", ""),
        answer_lang=state.get("answer_lang", "de"),
        confidence=float(state.get("confidence", 0.0)),
        attempts=int(state.get("attempts", 0)),
        claims=state.get("claims", []),
        artifact_chunks=state.get("artifact_chunks", []),
    )


def _run_ingest_job(job_id: str, tmp_path: Path) -> None:
    from src.ingest.pipeline import ingest

    job = _ingest_jobs[job_id]
    job.status = "running"
    try:
        with _ingest_lock:
            n = ingest(str(tmp_path))
            _refresh_bm25_indices()
        global _bm25_loaded
        _bm25_loaded = True
        job.n_chunks = n
        job.status = "done"
    except Exception as e:
        job.status = "error"
        job.error = str(e)
    finally:
        tmp_path.unlink(missing_ok=True)


@app.post("/api/ingest", response_model=IngestJobStatus)
def ingest_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload a PDF and run the ingestion pipeline (parse -> chunk -> embed -> index).

    Runs in the background; poll GET /api/ingest/{job_id} for status. Re-uploading
    a PDF with the same doc_id (filename stem) supersedes the prior version, per
    CLAUDE.md versioning (is_current flag) — handled inside src.ingest.pipeline.ingest.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf files are accepted")

    # doc_id is derived from the filename stem (sanitized) so re-uploads
    # consistently target the same document for versioning.
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


@app.get("/api/ingest/{job_id}", response_model=IngestJobStatus)
def get_ingest_status(job_id: str):
    job = _ingest_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="ingest job not found")
    return job


@app.get("/api/originals/{doc_id}")
def get_original(doc_id: str):
    """Serve a source PDF by doc_id (internal originals endpoint, CLAUDE.md spec)."""
    # doc_id comes from our own index payloads, but guard against path traversal anyway.
    safe_name = Path(doc_id).name
    pdf_path = Path(ORIGINALS_DIR) / f"{safe_name}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="document not found")
    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path.name)
