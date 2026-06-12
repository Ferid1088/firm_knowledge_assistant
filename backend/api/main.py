"""FastAPI application entry point.

Start: uvicorn backend.api.main:app --reload
"""
from __future__ import annotations
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.services.tracing import describe_langfuse_status
from backend.api.routes import chat, ingest, documents, config as config_route

logger = logging.getLogger(__name__)

app = FastAPI(title="Local RAG API")

# Pilot: Next.js dev server on localhost:3000. Internal-only origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(config_route.router, prefix="/api")


@app.on_event("startup")
def log_runtime_diagnostics() -> None:
    logger.info(describe_langfuse_status())
