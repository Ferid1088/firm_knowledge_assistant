"""FastAPI backend for the Next.js + assistant-ui frontend.

Backend is frontend-agnostic: this module is the API; the UI is a thin layer
over artifact_chunks (CLAUDE.md architecture principle). The LangGraph engine
(backend/graph/graph.py) does all orchestration; this file adapts HTTP <-> graph
for queries, and HTTP <-> backend/tools/pipeline.py for document ingestion.

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

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.config import ORIGINALS_DIR, AVAILABLE_LANGUAGES, OLLAMA_MODEL, RETRIEVE_K
from backend.api.routes import auth as auth_routes, admin as admin_routes
from backend.database import init_db
from backend.services import iam, conversations, sharing, rate_limit
from backend.services.conversations import ConversationError
from backend.services.rate_limit import RateLimitError

app = FastAPI(title="Local RAG API")

# Pilot: Next.js dev server runs on localhost:3000. Internal-only origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
    allow_credentials=True,
)


app.include_router(auth_routes.router)
app.include_router(admin_routes.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    iam.init_seed_data()


def get_current_user(request: Request) -> iam.User:
    """Resolve calling user from session cookie. Raises 401 if missing or expired."""
    from backend.services.auth import resolve_session
    session_id = request.cookies.get("rag_session", "")
    session = resolve_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = iam.get_user(session["user_id"])
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


_bm25_loaded = False
# Serializes ingestion jobs: BM25 rebuild + Qdrant writes are not safe to
# interleave across concurrent /api/ingest calls.
_ingest_lock = threading.Lock()


def _refresh_bm25_indices() -> None:
    from backend.tools.pipeline import rebuild_bm25_indices
    from backend.graph.nodes import set_bm25_indices

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
    from backend.graph.graph import run as graph_run

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


# ── IAM (read-only; for the frontend user-switcher) ──────────────────────────

@app.get("/api/users")
def list_users():
    return [{"id": u.id, "name": u.name, "department_id": u.department_id, "role": u.role} for u in iam.list_users()]


@app.get("/api/departments")
def list_departments():
    return iam.list_departments()


# ── Conversations ──────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    title: Optional[str] = "New conversation"


class ConversationRename(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None  # "active" | "archived" | "deleted" (set via PATCH)


class ShareRequest(BaseModel):
    user_id: str
    permission: str  # "view" | "comment" | "edit"


def _conversation_summary(conv: dict) -> dict:
    return {
        "id": conv["id"],
        "title": conv["title"],
        "status": conv["status"],
        "owner_user_id": conv["owner_user_id"],
        "department_id": conv["department_id"],
        "created_at": conv["created_at"],
        "updated_at": conv["updated_at"],
    }


@app.post("/api/conversations")
def create_conversation(req: ConversationCreate, user: iam.User = Depends(get_current_user)):
    try:
        rate_limit.apply_agent_rate_limits(user.id, "conversation")
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    conv = conversations.create_conversation(user, req.title or "New conversation")
    return _conversation_summary(conv)


@app.get("/api/conversations")
def list_conversations_endpoint(user: iam.User = Depends(get_current_user)):
    return [_conversation_summary(c) for c in conversations.list_conversations(user)]


@app.get("/api/conversations/{conversation_id}")
def get_conversation_endpoint(conversation_id: str, user: iam.User = Depends(get_current_user)):
    try:
        conv = conversations.get_conversation(conversation_id, user)
    except ConversationError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 403, detail=str(e))
    return {
        **_conversation_summary(conv),
        "messages": conversations.get_messages(conversation_id),
        "shares": sharing.list_shares(conversation_id),
    }


@app.patch("/api/conversations/{conversation_id}")
def update_conversation(conversation_id: str, req: ConversationRename, user: iam.User = Depends(get_current_user)):
    try:
        if req.title is not None:
            conversations.rename_conversation(conversation_id, user, req.title)
        if req.status is not None:
            if req.status == "archived":
                conversations.archive_conversation(conversation_id, user)
            elif req.status == "deleted":
                conversations.delete_conversation(conversation_id, user)
            elif req.status == "active":
                conversations.restore_conversation(conversation_id, user)
            else:
                raise HTTPException(status_code=400, detail="status must be one of: active, archived, deleted")
        return _conversation_summary(conversations.get_conversation_row(conversation_id))
    except ConversationError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 403, detail=str(e))


@app.post("/api/conversations/{conversation_id}/share")
def share_conversation_endpoint(conversation_id: str, req: ShareRequest, user: iam.User = Depends(get_current_user)):
    try:
        return sharing.share_conversation(conversation_id, user, req.user_id, req.permission)
    except ConversationError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/conversations/{conversation_id}/share/{target_user_id}")
def revoke_share_endpoint(conversation_id: str, target_user_id: str, user: iam.User = Depends(get_current_user)):
    try:
        sharing.revoke_share(conversation_id, user, target_user_id)
        return {"ok": True}
    except ConversationError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 403, detail=str(e))


@app.post("/api/conversations/{conversation_id}/messages", response_model=ChatResponse)
def post_message(conversation_id: str, req: ChatRequest, user: iam.User = Depends(get_current_user)):
    """Conversation-scoped chat: access check -> rate limit -> run graph with
    history -> persist both turns (encrypted, signed) -> return ChatResponse."""
    from backend.graph.graph import run as graph_run

    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    try:
        conversations.get_conversation(conversation_id, user)  # access check
        history = conversations.get_conversation_context(conversation_id, user)
    except ConversationError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 403, detail=str(e))

    try:
        rate_limit.apply_agent_rate_limits(user.id, "message")
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))

    _ensure_bm25_loaded()
    state = graph_run(req.question, active_lang_codes=req.active_lang_codes or ["de"], history=history)

    conversations.add_message(conversation_id, "user", req.question, state.get("query_lang", "de"))
    conversations.add_message(
        conversation_id, "assistant", state.get("answer", ""), state.get("answer_lang", "de"),
        claims=state.get("claims", []), artifact_chunks=state.get("artifact_chunks", []),
    )

    return ChatResponse(
        answer=state.get("answer", ""),
        answer_lang=state.get("answer_lang", "de"),
        confidence=float(state.get("confidence", 0.0)),
        attempts=int(state.get("attempts", 0)),
        claims=state.get("claims", []),
        artifact_chunks=state.get("artifact_chunks", []),
    )


def _run_ingest_job(job_id: str, tmp_path: Path) -> None:
    from backend.tools.pipeline import ingest

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
    CLAUDE.md versioning (is_current flag) — handled inside backend.tools.pipeline.ingest.
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
