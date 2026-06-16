from datetime import datetime, timedelta, timezone

from backend.database import get_connection
from backend.services import iam
from backend.services.conversations import create_conversation
from backend.services.sessions import create_agent_session, validate_session


def _conversation_id(db):
    alice = iam.get_user("user-alice")
    return create_conversation(alice, "Session test")["id"]


def test_valid_session_returns_user_and_conversation(db):
    conv_id = _conversation_id(db)
    session = create_agent_session("user-alice", conv_id)

    result = validate_session(session["session_id"])
    assert result == {"user_id": "user-alice", "conversation_id": conv_id}


def test_expired_session_fails_validation_and_is_removed(db):
    conv_id = _conversation_id(db)
    session = create_agent_session("user-alice", conv_id)
    session_id = session["session_id"]

    # Force the session into the past.
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    conn = get_connection()
    conn.execute(
        "UPDATE agent_sessions SET expires_at = ? WHERE session_id = ?",
        (expired_at, session_id),
    )
    conn.commit()
    conn.close()

    assert validate_session(session_id) is None

    # Expired session is pruned on access.
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM agent_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    conn.close()
    assert row is None


def test_unknown_session_returns_none(db):
    assert validate_session("does-not-exist") is None
