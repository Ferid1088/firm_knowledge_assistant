"""Conversation sharing: grant/revoke access to other users.

Owner-only operations (per the spec's sharing permissions API). Recipients
appear in `conversation_shares` and pass `can_access_conversation`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.database import get_connection
from backend.services import audit
from backend.services.conversations import get_conversation_row, ConversationError
from backend.services.iam import User, get_user


def _now() -> str:
    """Return current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def share_conversation(conversation_id: str, owner: User, target_user_id: str, permission: str) -> dict:
    """Grant target_user_id access to conversation_id with the given permission level."""
    if permission not in ("view", "comment", "edit"):
        raise ValueError("permission must be one of: view, comment, edit")

    conn = get_connection()
    try:
        conv = get_conversation_row(conversation_id, conn=conn)
        if conv["owner_user_id"] != owner.id:
            raise ConversationError("forbidden: only the owner can share a conversation")

        target = get_user(target_user_id)
        if target is None:
            raise ConversationError("target user not found")

        conn.execute(
            "INSERT INTO conversation_shares (conversation_id, user_id, permission, granted_by, granted_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(conversation_id, user_id) DO UPDATE SET permission = excluded.permission, "
            "granted_by = excluded.granted_by, granted_at = excluded.granted_at",
            (conversation_id, target_user_id, permission, owner.id, _now()),
        )
        audit.log_action(
            owner.id, conversation_id, "conversation_shared",
            {"target_user_id": target_user_id, "permission": permission}, conn=conn,
        )
        conn.commit()
        return {"conversation_id": conversation_id, "user_id": target_user_id, "permission": permission}
    finally:
        conn.close()


def revoke_share(conversation_id: str, owner: User, target_user_id: str) -> None:
    """Remove a conversation share; owner-only."""
    conn = get_connection()
    try:
        conv = get_conversation_row(conversation_id, conn=conn)
        if conv["owner_user_id"] != owner.id:
            raise ConversationError("forbidden: only the owner can revoke a share")

        conn.execute(
            "DELETE FROM conversation_shares WHERE conversation_id = ? AND user_id = ?",
            (conversation_id, target_user_id),
        )
        audit.log_action(
            owner.id, conversation_id, "conversation_share_revoked",
            {"target_user_id": target_user_id}, conn=conn,
        )
        conn.commit()
    finally:
        conn.close()


def list_shares(conversation_id: str) -> list[dict]:
    """Return all active share rows for a conversation."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM conversation_shares WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
