"""Conversation model: CRUD, lifecycle, and context-window management.

Implements the spec's conversation/message model against SQLite:
- Each conversation has its own DEK (generated at creation, wrapped with the
  local master key — see security.py).
- Messages are stored encrypted; content_hash + signature give integrity.
- ConversationContext builds the LLM-ready history within a token budget,
  reusing the Qwen3 tokenizer already used for embedding (token_count).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from backend.database import get_connection
from backend.config import DEFAULT_TENANT_ID, MAX_CONTEXT_TOKENS
from backend.services import security, audit
from backend.services.iam import User


def _now() -> str:
    """Return current UTC time as ISO-8601 string for DB timestamps."""
    return datetime.now(timezone.utc).isoformat()


class ConversationError(Exception):
    """Raised for not-found / forbidden conversation operations."""


# ── CRUD ───────────────────────────────────────────────────────────────────

def create_conversation(user: User, title: str = "New conversation") -> dict:
    """Create a new conversation with a fresh DEK and return the row as a dict.

    The DEK is generated locally, AES-GCM wrapped with the master key, and
    stored as ``wrapped_dek`` in the DB — plaintext DEK never persisted.
    """
    conv_id = str(uuid.uuid4())
    dek = security.generate_dek()
    wrapped = security.wrap_dek(dek)
    now = _now()

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO conversations "
            "(id, tenant_id, department_id, owner_user_id, title, status, wrapped_dek, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?)",
            (conv_id, DEFAULT_TENANT_ID, user.department_id, user.id, title, wrapped, now, now),
        )
        audit.log_action(user.id, conv_id, "conversation_created", {"title": title}, conn=conn)
        conn.commit()
        return get_conversation_row(conv_id, conn=conn)
    finally:
        conn.close()


def get_conversation_row(conversation_id: str, conn=None) -> dict:
    """Fetch a raw conversation row without access-control checks.

    Internal helper used by message operations that have already verified access
    at the API layer. Never call this directly from an API route handler.
    """
    own_conn = conn is None
    conn = conn or get_connection()
    try:
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if row is None:
            raise ConversationError("conversation not found")
        return dict(row)
    finally:
        if own_conn:
            conn.close()


def get_conversation(conversation_id: str, user: User) -> dict:
    """Access-checked fetch. Raises ConversationError if not found/forbidden."""
    from backend.services.iam import can_access_conversation

    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if row is None:
            raise ConversationError("conversation not found")
        conv = dict(row)
        if conv["status"] == "deleted" and conv["owner_user_id"] != user.id:
            raise ConversationError("conversation not found")
        if not can_access_conversation(user, conv, conn=conn):
            raise ConversationError("forbidden")
        return conv
    finally:
        conn.close()


def list_conversations(user: User) -> list[dict]:
    """Return all non-deleted conversations the user owns or has been shared into."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT c.* FROM conversations c "
            "LEFT JOIN conversation_shares s ON s.conversation_id = c.id AND s.user_id = ? "
            "WHERE c.status != 'deleted' "
            "AND (c.owner_user_id = ? OR s.user_id IS NOT NULL) "
            "ORDER BY c.updated_at DESC",
            (user.id, user.id),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Messages ───────────────────────────────────────────────────────────────

def add_message(
    conversation_id: str,
    role: str,
    text: str,
    lang: str,
    claims: list[dict] | None = None,
    artifact_chunks: list[dict] | None = None,
) -> dict:
    """Encrypt and store a message; promote conversation status from draft → active.

    The message content is AES-GCM encrypted with the conversation's unwrapped DEK.
    A SHA-256 content hash and Ed25519 signature are stored alongside for integrity
    verification (``get_messages`` checks these on read).
    """
    conn = get_connection()
    try:
        conv = get_conversation_row(conversation_id, conn=conn)
        dek = security.unwrap_dek(conv["wrapped_dek"])

        ciphertext, nonce = security.encrypt_message(text, dek)
        digest = security.content_hash(text)
        signature = security.sign(digest)

        msg_id = str(uuid.uuid4())
        now = _now()
        conn.execute(
            "INSERT INTO messages "
            "(id, conversation_id, role, ciphertext, nonce, content_hash, signature, "
            " lang, claims_json, artifact_chunks_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                msg_id, conversation_id, role, ciphertext, nonce, digest, signature,
                lang, json.dumps(claims or []), json.dumps(artifact_chunks or []), now,
            ),
        )
        new_status = "active" if conv["status"] == "draft" else conv["status"]
        conn.execute(
            "UPDATE conversations SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, conversation_id),
        )
        audit.log_action(conv["owner_user_id"], conversation_id, f"message_added_{role}", conn=conn)
        conn.commit()
        return {
            "id": msg_id, "conversation_id": conversation_id, "role": role,
            "text": text, "lang": lang, "claims": claims or [],
            "artifact_chunks": artifact_chunks or [], "created_at": now,
        }
    finally:
        conn.close()


def get_messages(conversation_id: str) -> list[dict]:
    """All messages, decrypted, oldest first."""
    conn = get_connection()
    try:
        conv = get_conversation_row(conversation_id, conn=conn)
        dek = security.unwrap_dek(conv["wrapped_dek"])
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()

        messages = []
        for r in rows:
            row = dict(r)
            text = security.decrypt_message(row["ciphertext"], row["nonce"], dek)
            verified = audit.verify_message_integrity(row, text)
            messages.append({
                "id": row["id"],
                "role": row["role"],
                "text": text,
                "lang": row["lang"],
                "claims": json.loads(row["claims_json"] or "[]"),
                "artifact_chunks": json.loads(row["artifact_chunks_json"] or "[]"),
                "created_at": row["created_at"],
                "integrity_verified": verified,
            })
        return messages
    finally:
        conn.close()


# ── Context window management ───────────────────────────────────────────────

class ConversationContext:
    """Builds an LLM-ready history within a token budget (small-to-big over turns)."""

    def __init__(self, conversation_id: str, max_tokens: int = MAX_CONTEXT_TOKENS):
        """Bind to a conversation and set the token budget for context trimming."""
        self.conversation_id = conversation_id
        self.max_tokens = max_tokens

    def build(self) -> list[dict]:
        """Return [{role, text}, ...] oldest-first, dropping the oldest turns
        until the total fits within max_tokens."""
        from backend.adapters.embedder import load_embedder, token_count

        messages = get_messages(self.conversation_id)
        embedder = load_embedder()

        kept: list[dict] = []
        total = 0
        # Walk newest -> oldest, keep what fits, then restore chronological order.
        for msg in reversed(messages):
            t = token_count(embedder, msg["text"])
            if total + t > self.max_tokens and kept:
                break
            total += t
            kept.append({"role": msg["role"], "text": msg["text"]})

        kept.reverse()
        return kept


def get_conversation_context(conversation_id: str, user: User, max_tokens: int = MAX_CONTEXT_TOKENS) -> list[dict]:
    """Return the trimmed message history for a conversation after an access check."""
    get_conversation(conversation_id, user)  # access check
    return ConversationContext(conversation_id, max_tokens).build()


# ── Lifecycle ────────────────────────────────────────────────────────────────

def _set_status(conversation_id: str, user: User, new_status: str, action: str) -> dict:
    """Internal helper: set conversation status and emit an audit log entry."""
    from backend.services.iam import can_agent_act

    conn = get_connection()
    try:
        conv = get_conversation_row(conversation_id, conn=conn)
        if not can_agent_act(user, action, conv):
            raise ConversationError("forbidden")
        conn.execute(
            "UPDATE conversations SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, _now(), conversation_id),
        )
        audit.log_action(user.id, conversation_id, action, conn=conn)
        conn.commit()
        return get_conversation_row(conversation_id, conn=conn)
    finally:
        conn.close()


def archive_conversation(conversation_id: str, user: User) -> dict:
    """Move conversation to 'archived' status (reversible)."""
    return _set_status(conversation_id, user, "archived", "conversation_archived")


def delete_conversation(conversation_id: str, user: User) -> dict:
    """Soft delete — status=deleted, never hard-removed (audit trail intact)."""
    return _set_status(conversation_id, user, "deleted", "conversation_deleted")


def restore_conversation(conversation_id: str, user: User) -> dict:
    """Restore an archived conversation to 'active' status."""
    return _set_status(conversation_id, user, "active", "conversation_restored")


def rename_conversation(conversation_id: str, user: User, title: str) -> dict:
    """Update the conversation title (owner only)."""
    from backend.services.iam import can_agent_act

    conn = get_connection()
    try:
        conv = get_conversation_row(conversation_id, conn=conn)
        if not can_agent_act(user, "conversation_renamed", conv):
            raise ConversationError("forbidden")
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now(), conversation_id),
        )
        audit.log_action(user.id, conversation_id, "conversation_renamed", {"title": title}, conn=conn)
        conn.commit()
        return get_conversation_row(conversation_id, conn=conn)
    finally:
        conn.close()
