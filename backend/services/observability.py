"""Langfuse observability — self-hosted only (CLAUDE.md: never cloud).

Wraps the LangGraph run() call with a Langfuse trace so every query, its
retrieved chunks, rerank result, confidence score, and final answer are
visible in the Langfuse UI at http://localhost:3001.

Usage:
    from backend.services.observability import trace_run
    result = trace_run(question, active_lang_codes, history)

If Langfuse is disabled or unavailable, trace_run falls back to a plain
graph.run() call with zero overhead.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Lazy singleton — created once on first trace_run() call.
_client: Any = None
_enabled: bool | None = None  # None = not yet evaluated


def _get_client():
    """Return a Langfuse client, or None if disabled / package missing."""
    global _client, _enabled

    if _enabled is False:
        return None

    if _enabled is None:
        # Evaluate once. Read env at call time so the startup hook can load
        # .env.langfuse before this runs.
        enabled = os.environ.get("LANGFUSE_ENABLED", "false").lower() in ("1", "true", "yes")
        if not enabled:
            _enabled = False
            logger.info("[observability] Langfuse disabled (LANGFUSE_ENABLED != true)")
            return None

        host = os.environ.get("LANGFUSE_HOST", "http://localhost:3001")
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")

        if not public_key or not secret_key:
            _enabled = False
            logger.warning("[observability] Langfuse keys missing — tracing disabled")
            return None

        try:
            from langfuse import Langfuse
            _client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
            _enabled = True
            logger.info(f"[observability] Langfuse enabled → {host}")
        except Exception as exc:
            _enabled = False
            logger.warning(f"[observability] Langfuse init failed: {exc}")
            return None

    return _client


def trace_run(
    question: str,
    active_lang_codes: list[str] | None = None,
    history: list[dict] | None = None,
    allowed_doc_type_ids: list[str] | None = None,
    user_id: str | None = None,
    conversation_id: str | None = None,
) -> Any:
    """Run the RAG graph and emit a Langfuse trace if enabled."""
    from backend.graph.graph import run as graph_run

    client = _get_client()

    if client is None:
        return graph_run(question, active_lang_codes, history, allowed_doc_type_ids)

    trace = client.trace(
        name="rag_query",
        input={"question": question, "active_lang_codes": active_lang_codes},
        user_id=user_id,
        session_id=conversation_id,
        metadata={"conversation_id": conversation_id},
    )

    try:
        span = trace.span(name="graph.run", input={"question": question})
        result = graph_run(question, active_lang_codes, history, allowed_doc_type_ids)
        span.end(output={
            "answer": result.get("answer", ""),
            "confidence": result.get("confidence", 0),
            "attempts": result.get("attempts", 0),
            "n_chunks": len(result.get("artifact_chunks", [])),
        })
        trace.update(
            output={"answer": result.get("answer", ""), "confidence": result.get("confidence", 0)},
        )
        client.flush()
        return result

    except Exception as exc:
        trace.update(output={"error": str(exc)})
        client.flush()
        raise
