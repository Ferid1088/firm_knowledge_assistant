"""Agent session management — SQLite substitute for Redis-backed sessions.

Per the spec: create_agent_session() with a 1-hour TTL (SESSION_TTL_SECONDS).
Expiry is checked lazily on access; expired rows are pruned opportunistically.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from backend.database import get_connection
from backend.config import SESSION_TTL_SECONDS


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_agent_session(user_id: str, conversation_id: str) -> dict:
    session_id = uuid.uuid4().hex
    now = _now()
    expires_at = now + timedelta(seconds=SESSION_TTL_SECONDS)

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO agent_sessions (session_id, user_id, conversation_id, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, user_id, conversation_id, now.isoformat(), expires_at.isoformat()),
        )
        conn.commit()
        return {
            "session_id": session_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "expires_at": expires_at.isoformat(),
        }
    finally:
        conn.close()


def validate_session(session_id: str) -> dict | None:
    """Return {user_id, conversation_id} if the session exists and is unexpired,
    else None (and delete it if expired)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM agent_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None

        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= _now():
            conn.execute("DELETE FROM agent_sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            return None

        return {"user_id": row["user_id"], "conversation_id": row["conversation_id"]}
    finally:
        conn.close()


def cleanup_expired_sessions() -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM agent_sessions WHERE expires_at <= ?", (_now().isoformat(),)
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
