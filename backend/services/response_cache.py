"""SQLite-backed response cache for frequent identical queries.

Cache key = SHA-256 of (question, conversation_id, user_id,
                        sorted active_lang_codes, sorted allowed_doc_type_ids).
All five dimensions matter: same question in a different conversation has
different history context; different lang codes change BM25 passes; different
doc-type filters change what is retrieved.

Eviction is lazy (no background job):
- TTL: rows older than CACHE_TTL_SECONDS are deleted on each get/put.
- Max size: oldest-by-accessed_at rows are pruned when count > CACHE_MAX_ENTRIES.
- Confidence gate: only responses with confidence >= CACHE_MIN_CONFIDENCE are stored.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from backend.database import get_connection

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_key(
    question: str,
    conversation_id: str,
    user_id: str,
    active_lang_codes: list[str] | None,
    allowed_doc_type_ids: list[str] | None,
) -> str:
    """Return hex SHA-256 cache key for the given query parameters."""
    canonical = json.dumps(
        [
            question.strip().lower(),
            conversation_id,
            user_id,
            sorted(active_lang_codes or []),
            sorted(allowed_doc_type_ids or []),
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def get_cached(key: str) -> dict[str, Any] | None:
    """Return cached response dict if present and not expired, else None."""
    from backend.config import CACHE_TTL_SECONDS

    now = _now()
    with get_connection() as conn:
        _evict_expired(conn, now, CACHE_TTL_SECONDS)

        row = conn.execute(
            "SELECT response_json FROM response_cache WHERE cache_key = ?", (key,)
        ).fetchone()

        if row is None:
            return None

        conn.execute(
            "UPDATE response_cache SET accessed_at = ?, hit_count = hit_count + 1 WHERE cache_key = ?",
            (now, key),
        )

    try:
        result = json.loads(row["response_json"])
        logger.info(f"[cache] HIT key={key[:12]}…")
        return result
    except Exception as exc:
        logger.warning(f"[cache] Failed to deserialise cached entry: {exc}")
        return None


def put_cache(
    key: str,
    response: dict[str, Any],
    question: str,
    conversation_id: str,
    user_id: str,
    active_lang_codes: list[str] | None,
    allowed_doc_type_ids: list[str] | None,
    confidence: float,
) -> None:
    """Store a response dict in the cache if it meets the confidence threshold."""
    from backend.config import CACHE_MIN_CONFIDENCE, CACHE_MAX_ENTRIES, CACHE_TTL_SECONDS

    if confidence < CACHE_MIN_CONFIDENCE:
        logger.debug(f"[cache] SKIP (confidence {confidence:.2f} < {CACHE_MIN_CONFIDENCE})")
        return

    now = _now()
    response_json = json.dumps(response, ensure_ascii=False)

    with get_connection() as conn:
        _evict_expired(conn, now, CACHE_TTL_SECONDS)
        _evict_lru_if_needed(conn, CACHE_MAX_ENTRIES)

        conn.execute(
            """INSERT INTO response_cache
               (cache_key, conversation_id, user_id, query_hash,
                response_json, confidence, created_at, accessed_at, hit_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
               ON CONFLICT(cache_key) DO UPDATE SET
                   response_json = excluded.response_json,
                   confidence    = excluded.confidence,
                   accessed_at   = excluded.accessed_at
            """,
            (key, conversation_id, user_id,
             hashlib.sha256(question.strip().lower().encode()).hexdigest(),
             response_json, confidence, now, now),
        )

    logger.info(f"[cache] STORED key={key[:12]}… confidence={confidence:.2f}")


def _evict_expired(conn: Any, now: str, ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        return
    from datetime import timedelta
    cutoff = datetime.fromisoformat(now) - timedelta(seconds=ttl_seconds)
    conn.execute(
        "DELETE FROM response_cache WHERE created_at < ?",
        (cutoff.isoformat(),),
    )


def _evict_lru_if_needed(conn: Any, max_entries: int) -> None:
    if max_entries <= 0:
        return
    count = conn.execute("SELECT COUNT(*) FROM response_cache").fetchone()[0]
    if count < max_entries:
        return
    evict_n = max(1, max_entries // 10)
    conn.execute(
        """DELETE FROM response_cache WHERE cache_key IN (
               SELECT cache_key FROM response_cache
               ORDER BY accessed_at ASC LIMIT ?
           )""",
        (evict_n,),
    )
    logger.info(f"[cache] Evicted {evict_n} LRU entries (was {count} / {max_entries})")
