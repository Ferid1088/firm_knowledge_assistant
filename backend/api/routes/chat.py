"""POST /api/chat"""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import DEFAULT_ANSWER_LANG

router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    active_lang_codes: Optional[list[str]] = None


class ChatResponse(BaseModel):
    answer: str
    answer_lang: str
    confidence: float
    attempts: int
    supporting_points: list[str]
    caveats: list[str]
    claims: list[dict]
    artifact_chunks: list[dict]


def _ensure_bm25_loaded() -> None:
    from backend.tools.pdf_ingest import rebuild_bm25_indices
    from backend.services.model_registry import get_bm25_indices, set_bm25_indices
    if not get_bm25_indices():
        set_bm25_indices(rebuild_bm25_indices())


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    from backend.graph.graph import run as graph_run
    _ensure_bm25_loaded()
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    state = graph_run(req.question, active_lang_codes=req.active_lang_codes or ["de"])
    return ChatResponse(
        answer=state.get("answer", ""),
        answer_lang=state.get("answer_lang", DEFAULT_ANSWER_LANG),
        confidence=float(state.get("confidence", 0.0)),
        attempts=int(state.get("attempts", 0)),
        supporting_points=state.get("supporting_points", []),
        caveats=state.get("caveats", []),
        claims=state.get("claims", []),
        artifact_chunks=state.get("artifact_chunks", []),
    )
