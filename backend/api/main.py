"""FastAPI backend for the Next.js + assistant-ui frontend.

Backend is frontend-agnostic: this module is the API; the UI is a thin layer
over artifact_chunks (CLAUDE.md architecture principle). The LangGraph engine
(backend/graph/graph.py) does all orchestration; this file adapts HTTP <-> graph
for queries, and HTTP <-> backend/tools/pipeline.py for document ingestion.

Air-gap: CORS restricted to the local Next.js dev origin; offline/telemetry
flags are set in config.py (imported on module load).
"""
from __future__ import annotations

import os
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Optional

# Load .env.langfuse early so config.py sees the env vars when it imports.
def _bootstrap_langfuse_env() -> None:
    """Load .env.langfuse into os.environ before config.py reads LANGFUSE_* variables."""
    env_file = Path(".env.langfuse")
    if not env_file.exists():
        return
    with env_file.open() as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _key, _, _val = _line.partition("=")
            os.environ.setdefault(_key.strip(), _val.strip())

_bootstrap_langfuse_env()

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.config import ORIGINALS_DIR, AVAILABLE_LANGUAGES, OLLAMA_MODEL, RETRIEVE_K, CORS_ALLOWED_ORIGINS
from backend.api.routes import auth as auth_routes, admin as admin_routes
from backend.database import init_db
from backend.services import iam, conversations, sharing, rate_limit
from backend.services.conversations import ConversationError
from backend.services.rate_limit import RateLimitError

app = FastAPI(title="Local RAG API")

# Pilot: Next.js dev server runs on localhost:3000. Internal-only origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
    allow_credentials=True,
)


app.include_router(auth_routes.router)
app.include_router(admin_routes.router)


@app.on_event("startup")
def _startup() -> None:
    """FastAPI lifespan startup: init DB schema, seed IAM data, and load Langfuse env."""
    # Load Langfuse env vars before config reads them
    _load_langfuse_env()
    init_db()
    iam.init_seed_data()


def _load_langfuse_env() -> None:
    """Load .env.langfuse into os.environ if it exists (must run before config import)."""
    import os
    env_file = Path(".env.langfuse")
    if not env_file.exists():
        return
    with env_file.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


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
    """Rebuild BM25 indices from Qdrant and push them into the graph node cache."""
    from backend.tools.pipeline import rebuild_bm25_indices
    from backend.graph.retrieval.nodes import set_bm25_indices

    set_bm25_indices(rebuild_bm25_indices())


def _ensure_bm25_loaded() -> None:
    """BM25 indices are not persisted with Qdrant; rebuild once per process."""
    global _bm25_loaded
    if _bm25_loaded:
        return
    _refresh_bm25_indices()
    _bm25_loaded = True


class ChatRequest(BaseModel):
    """Incoming chat message with optional language and doc-type filters."""

    question: str
    active_lang_codes: Optional[list[str]] = None
    doc_type_filter: Optional[list[str]] = None  # user-selected type filter; None = all allowed
    structural_types: Optional[list[str]] = None  # e.g. ["table", "list"] — filter by chunk structure
    date_from: Optional[str] = None   # ISO date filter lower bound (inclusive)
    date_to: Optional[str] = None     # ISO date filter upper bound (inclusive)


class ChatResponse(BaseModel):
    """Response returned by /api/chat and /api/conversations/{id}/messages."""

    answer: str
    answer_lang: str
    confidence: float
    attempts: int
    claims: list[dict]
    artifact_chunks: list[dict]


class IngestJobStatus(BaseModel):
    """Live status of a background ingestion job returned by /api/ingest/{job_id}."""

    job_id: str
    status: str  # "queued" | "running" | "done" | "error"
    doc_id: str
    n_chunks: Optional[int] = None
    doc_type: Optional[str] = None
    doc_type_confidence: Optional[float] = None
    parser_name: Optional[str] = None
    chunker_name: Optional[str] = None
    is_scanned: Optional[bool] = None
    department_ids: Optional[list[str]] = None
    error: Optional[str] = None


# In-memory job tracking (pilot scope; one process). Keyed by job_id.
_ingest_jobs: dict[str, IngestJobStatus] = {}


@app.get("/api/doc-types")
def list_doc_types(user: iam.User = Depends(get_current_user)):
    """Return active document types. Filtered to the user's allowed set if restricted."""
    from backend.services.admin import list_doc_types_admin
    all_active = list_doc_types_admin(active_only=True)
    allowed = user.allowed_doc_type_ids
    if allowed is None:
        return all_active
    return [dt for dt in all_active if dt["id"] in allowed]


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
def chat(req: ChatRequest, user: iam.User = Depends(get_current_user)):
    """Stateless single-turn chat: run the full RAG graph and return the answer."""
    from backend.services.observability import trace_run

    _ensure_bm25_loaded()

    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    state = trace_run(
        req.question,
        active_lang_codes=req.active_lang_codes or ["de"],
        allowed_doc_type_ids=user.allowed_doc_type_ids,
        user_id=user.id,
        structural_types=req.structural_types,
        date_from=req.date_from,
        date_to=req.date_to,
    )

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
    """Return all users as lightweight dicts for the frontend user-switcher."""
    return [{"id": u.id, "name": u.name, "department_id": u.department_id, "role": u.role} for u in iam.list_users()]


@app.get("/api/departments")
def list_departments():
    """Return all departments (used to populate dropdowns in the upload modal)."""
    return iam.list_departments()


@app.get("/api/departments/allowed")
def list_allowed_departments(request: Request):
    """Return departments the current user may filter by (respects user_department_permissions)."""
    from backend.services.admin import get_user_department_ids
    from backend.services.auth import resolve_session as _resolve_session
    session_id = request.cookies.get("rag_session", "")
    session = _resolve_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = iam.get_user(session["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    all_depts = iam.list_departments()
    active = [d for d in all_depts if d.get("status") == "active"]
    if user.role_id == "superadmin":
        return active
    allowed_ids = get_user_department_ids(user.id)
    if allowed_ids is None:
        return active  # no restriction → all active
    return [d for d in active if d["id"] in allowed_ids]


# ── Conversations ──────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    """Request body for POST /api/conversations."""

    title: Optional[str] = "New conversation"


class ConversationRename(BaseModel):
    """Request body for PATCH /api/conversations/{id} — rename or change status."""

    title: Optional[str] = None
    status: Optional[str] = None  # "active" | "archived" | "deleted" (set via PATCH)


class ShareRequest(BaseModel):
    """Request body for POST /api/conversations/{id}/share."""

    user_id: str
    permission: str  # "view" | "comment" | "edit"


def _conversation_summary(conv: dict) -> dict:
    """Extract the public-facing subset of a conversation row (no messages, no shares)."""
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
    """Create a new conversation; enforces the per-day rate limit before creation."""
    try:
        rate_limit.apply_agent_rate_limits(user.id, "conversation")
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    conv = conversations.create_conversation(user, req.title or "New conversation")
    return _conversation_summary(conv)


@app.get("/api/conversations")
def list_conversations_endpoint(user: iam.User = Depends(get_current_user)):
    """Return summary rows for all active conversations visible to the current user."""
    return [_conversation_summary(c) for c in conversations.list_conversations(user)]


@app.get("/api/conversations/{conversation_id}")
def get_conversation_endpoint(conversation_id: str, user: iam.User = Depends(get_current_user)):
    """Return full conversation data including decrypted messages and share list."""
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
    """Rename a conversation or change its status (active/archived/deleted)."""
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
    """Share a conversation with another user at the specified permission level."""
    try:
        return sharing.share_conversation(conversation_id, user, req.user_id, req.permission)
    except ConversationError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/conversations/{conversation_id}/share/{target_user_id}")
def revoke_share_endpoint(conversation_id: str, target_user_id: str, user: iam.User = Depends(get_current_user)):
    """Revoke a previously granted share for the given target user."""
    try:
        sharing.revoke_share(conversation_id, user, target_user_id)
        return {"ok": True}
    except ConversationError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 403, detail=str(e))


@app.post("/api/conversations/{conversation_id}/messages", response_model=ChatResponse)
def post_message(conversation_id: str, req: ChatRequest, user: iam.User = Depends(get_current_user)):
    """Conversation-scoped chat: access check -> rate limit -> run graph with
    history -> persist both turns (encrypted, signed) -> return ChatResponse."""
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

    # Compute effective doc-type filter: intersection of what the user is allowed
    # to see with what they chose to filter by. Neither can expand the other.
    effective_doc_types: list[str] | None
    if user.allowed_doc_type_ids is not None and req.doc_type_filter:
        effective_doc_types = [i for i in req.doc_type_filter if i in user.allowed_doc_type_ids]
    elif user.allowed_doc_type_ids is not None:
        effective_doc_types = user.allowed_doc_type_ids
    elif req.doc_type_filter:
        effective_doc_types = req.doc_type_filter
    else:
        effective_doc_types = None  # unrestricted

    _ensure_bm25_loaded()

    from backend.services.observability import trace_run
    from backend.services.response_cache import compute_key, get_cached, put_cache
    from backend.config import CACHE_ENABLED

    active_langs = req.active_lang_codes or ["de"]
    cache_hit = False
    _cache_key: str | None = None

    if CACHE_ENABLED:
        _cache_key = compute_key(req.question, conversation_id, user.id,
                                 active_langs, effective_doc_types)
        state = get_cached(_cache_key)
        if state is not None:
            cache_hit = True

    if not cache_hit:
        state = trace_run(
            req.question,
            active_lang_codes=active_langs,
            history=history,
            allowed_doc_type_ids=effective_doc_types,
            user_id=user.id,
            conversation_id=conversation_id,
            structural_types=req.structural_types,
            date_from=req.date_from,
            date_to=req.date_to,
        )
        if CACHE_ENABLED and _cache_key is not None:
            put_cache(_cache_key, state, req.question, conversation_id, user.id,
                      active_langs, effective_doc_types, float(state.get("confidence", 0)))

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


def _run_ingest_job(
    job_id: str, tmp_path: Path,
    doc_type_id: str | None = None,
    department_ids: list[str] | None = None,
    user_id: str = "",
    original_filename: str = "",
    client_ip: str = "",
    user_agent: str = "",
) -> None:
    """Background worker: run full ingest pipeline, update the job status dict, then audit-log."""
    from backend.tools.pipeline import ingest
    import json as _json

    job = _ingest_jobs[job_id]
    job.status = "running"
    try:
        # Detect type BEFORE acquiring the lock so the frontend can show it immediately.
        resolved_doc_type = doc_type_id
        if not resolved_doc_type:
            from backend.tools.type_detector import detect_type
            tr = detect_type(str(tmp_path))
            resolved_doc_type = tr.doc_type
            job.doc_type = resolved_doc_type
            job.doc_type_confidence = tr.confidence

        with _ingest_lock:
            result = ingest(str(tmp_path), doc_type_id=resolved_doc_type,
                            department_ids=department_ids or [])
            if result.is_scanned:
                job.status = "error"
                job.error = "PDF is scanned (no text layer). OCR path not yet built."
                job.is_scanned = True
                job.doc_type = result.doc_type
                return
            _refresh_bm25_indices()
        global _bm25_loaded
        _bm25_loaded = True
        job.n_chunks = result.n_chunks
        job.doc_type = result.doc_type
        job.doc_type_confidence = result.doc_type_confidence
        job.parser_name = result.parser_name
        job.chunker_name = result.chunker_name
        job.is_scanned = result.is_scanned
        job.department_ids = department_ids or None
        job.status = "done"
    except Exception as e:
        job.status = "error"
        job.error = str(e)
    finally:
        tmp_path.unlink(missing_ok=True)

    # Audit log — record regardless of success/failure
    try:
        from backend.database import get_connection
        import datetime
        conn = get_connection()
        conn.execute(
            """INSERT INTO audit_log
               (user_id, action, details_json, resource_type, decision, ip_address, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                user_id,
                "ingest_document",
                _json.dumps({
                    "filename": original_filename,
                    "doc_type_id": doc_type_id,
                    "doc_type_resolved": job.doc_type,
                    "n_chunks": job.n_chunks,
                    "status": job.status,
                    "error": job.error,
                    "user_agent": user_agent,
                }),
                "document",
                job.status,
                client_ip,
                datetime.datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # audit failure never blocks the main result


@app.post("/api/ingest", response_model=IngestJobStatus)
def ingest_document(request: Request, background_tasks: BackgroundTasks,
                    file: UploadFile = File(...),
                    doc_type_id: Optional[str] = Query(default=None),
                    department_ids: Optional[str] = Query(default=None),
                    user: iam.User = Depends(get_current_user)):
    """Upload a document and run the ingestion pipeline (parse -> chunk -> embed -> index).

    doc_type_id: auto-detected by the pipeline; optional override.
    department_ids: comma-separated department IDs selected at upload time.
    Runs in the background; poll GET /api/ingest/{job_id} for status.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="no filename provided")

    suffix = Path(file.filename).suffix.lower()
    _ALLOWED_EXTENSIONS = {
        ".pdf", ".docx", ".xlsx", ".xls", ".csv", ".txt", ".md",
        ".html", ".htm", ".eml", ".png", ".jpg", ".jpeg", ".tiff", ".tif",
    }
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"unsupported file type: {suffix}")

    doc_id = re.sub(r"[^A-Za-z0-9_-]", "_", Path(file.filename).stem) or "doc"

    staging_dir = Path(ORIGINALS_DIR) / "_staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = staging_dir / f"{doc_id}{suffix}"
    with tmp_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Capture upload metadata for audit log
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() \
        or (request.client.host if request.client else "unknown")
    user_agent = request.headers.get("user-agent", "")

    dept_ids: list[str] = [d.strip() for d in department_ids.split(",") if d.strip()] \
        if department_ids else []

    job_id = uuid.uuid4().hex
    _ingest_jobs[job_id] = IngestJobStatus(
        job_id=job_id, status="queued", doc_id=doc_id,
        doc_type=doc_type_id, department_ids=dept_ids or None,
    )
    background_tasks.add_task(
        _run_ingest_job, job_id, tmp_path, doc_type_id, dept_ids,
        user.id, file.filename, client_ip, user_agent,
    )
    return _ingest_jobs[job_id]


@app.get("/api/ingest/{job_id}", response_model=IngestJobStatus)
def get_ingest_status(job_id: str):
    """Poll the in-memory status of a background ingestion job."""
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
