"""Audit trail and message-integrity verification.

Substitutes the spec's RSA-signed audit trail: every mutating action is
logged, and every message's content_hash + Ed25519 signature can be
re-verified against its decrypted content.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.database import get_connection
from backend.services import security


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_action(
    user_id: str,
    conversation_id: str | None,
    action: str,
    details: dict | None = None,
    conn=None,
    resource_type: str | None = None,
    decision: str | None = None,
    ip_address: str | None = None,
) -> None:
    own_conn = conn is None
    conn = conn or get_connection()
    try:
        conn.execute(
            "INSERT INTO audit_log "
            "(user_id, conversation_id, action, details_json, "
            "resource_type, decision, ip_address, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (user_id, conversation_id, action, json.dumps(details) if details else None,
             resource_type, decision, ip_address, datetime.now(timezone.utc).isoformat()),
        )
        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()


def verify_message_integrity(message_row: dict, plaintext: str) -> bool:
    """Recompute content_hash from decrypted plaintext and verify the signature.

    Returns False if either the hash or the signature no longer match —
    i.e. the stored ciphertext/hash/signature was tampered with.
    """
    expected_hash = security.content_hash(plaintext)
    if expected_hash != message_row["content_hash"]:
        return False
    return security.verify(message_row["content_hash"], message_row["signature"])
