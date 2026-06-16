"""Agent rate limiting — SQLite substitute for Redis-backed counters.

Fixed-window counters per user:
- "message": RATE_LIMIT_MSGS_PER_HOUR, window = current hour
- "conversation": RATE_LIMIT_CONVERSATIONS_PER_DAY, window = current day

apply_agent_rate_limits() increments the counter and raises RateLimitError if
the limit is exceeded — mapped to HTTP 429 in the API layer.
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.database import get_connection
from backend.config import RATE_LIMIT_MSGS_PER_HOUR, RATE_LIMIT_CONVERSATIONS_PER_DAY

_WINDOWS = {
    "message": ("message_hourly", "%Y-%m-%dT%H", RATE_LIMIT_MSGS_PER_HOUR),
    "conversation": ("conversation_daily", "%Y-%m-%d", RATE_LIMIT_CONVERSATIONS_PER_DAY),
}


class RateLimitError(Exception):
    def __init__(self, kind: str, limit: int):
        self.kind = kind
        self.limit = limit
        super().__init__(f"rate limit exceeded for '{kind}': max {limit} per window")


def apply_agent_rate_limits(user_id: str, kind: str) -> None:
    """Increment the counter for `kind` ('message' | 'conversation') and raise
    RateLimitError if the configured limit is exceeded."""
    window_type, fmt, limit = _WINDOWS[kind]
    window_start = datetime.now(timezone.utc).strftime(fmt)

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT count FROM rate_limit_counters WHERE key = ? AND window_type = ? AND window_start = ?",
            (user_id, window_type, window_start),
        ).fetchone()
        current = row["count"] if row else 0

        if current >= limit:
            raise RateLimitError(kind, limit)

        conn.execute(
            "INSERT INTO rate_limit_counters (key, window_type, window_start, count) "
            "VALUES (?, ?, ?, 1) "
            "ON CONFLICT(key, window_type, window_start) DO UPDATE SET count = count + 1",
            (user_id, window_type, window_start),
        )
        conn.commit()
    finally:
        conn.close()


def get_usage(user_id: str, kind: str) -> dict:
    window_type, fmt, limit = _WINDOWS[kind]
    window_start = datetime.now(timezone.utc).strftime(fmt)

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT count FROM rate_limit_counters WHERE key = ? AND window_type = ? AND window_start = ?",
            (user_id, window_type, window_start),
        ).fetchone()
        return {"used": row["count"] if row else 0, "limit": limit}
    finally:
        conn.close()
