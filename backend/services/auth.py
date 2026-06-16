"""Authentication: password hashing, session management, login rate limiting.

pyotp is imported but never called (Phase 2 MFA).
"""
from __future__ import annotations

import hashlib
import secrets
import base64
from datetime import datetime, timezone, timedelta

import pyotp  # noqa: F401  — Phase 2; imported to surface missing-dep errors early

from backend.database import get_connection

_ITERATIONS = 260_000
_SESSION_TTL_HOURS = 8
_LOGIN_WINDOW_MINUTES = 15
_LOGIN_MAX_ATTEMPTS = 5

# Dummy hash for timing-safe "user not found" path
_DUMMY_HASH = (
    "pbkdf2_sha256$"
    + base64.b64encode(b"\x00" * 32).decode()
    + "$"
    + base64.b64encode(b"\x00" * 32).decode()
)


def hash_password(password: str) -> str:
    """Return pbkdf2_sha256$<base64-salt>$<base64-hash>."""
    salt = secrets.token_bytes(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return (
        "pbkdf2_sha256$"
        + base64.b64encode(salt).decode()
        + "$"
        + base64.b64encode(dk).decode()
    )


def verify_password(password: str, stored_hash: str) -> bool:
    """Timing-safe password verification. Returns False for empty stored_hash."""
    if not stored_hash:
        # Run a dummy hash to maintain constant time
        _constant_time_dummy(password)
        return False
    try:
        _, b64_salt, b64_hash = stored_hash.split("$")
        salt = base64.b64decode(b64_salt)
        expected = base64.b64decode(b64_hash)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
        return secrets.compare_digest(dk, expected)
    except Exception:
        return False


def _constant_time_dummy(password: str) -> None:
    """Run a full PBKDF2 round against the dummy hash to prevent timing oracle."""
    try:
        _, b64_salt, b64_hash = _DUMMY_HASH.split("$")
        salt = base64.b64decode(b64_salt)
        expected = base64.b64decode(b64_hash)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
        secrets.compare_digest(dk, expected)
    except Exception:
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Login rate limiting (IP-based) ───────────────────────────────────────────

def _window_start_login() -> str:
    """Current 15-minute window start."""
    now = datetime.now(timezone.utc)
    minutes_block = (now.minute // _LOGIN_WINDOW_MINUTES) * _LOGIN_WINDOW_MINUTES
    return now.replace(minute=minutes_block, second=0, microsecond=0).isoformat()


def check_login_rate_limit(ip: str) -> None:
    """Raise ValueError if IP exceeded limit. Call BEFORE verifying credentials."""
    key = f"login_ip_{ip}"
    window = _window_start_login()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT count FROM rate_limit_counters WHERE key=? AND window_type='login' AND window_start=?",
            (key, window),
        ).fetchone()
        if row and row[0] >= _LOGIN_MAX_ATTEMPTS:
            raise ValueError("Too many login attempts. Try again in 15 minutes.")
    finally:
        conn.close()


def increment_login_attempts(ip: str) -> None:
    key = f"login_ip_{ip}"
    window = _window_start_login()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO rate_limit_counters (key, window_type, window_start, count) VALUES (?,?,?,1)
               ON CONFLICT(key, window_type, window_start) DO UPDATE SET count = count + 1""",
            (key, "login", window),
        )
        conn.commit()
    finally:
        conn.close()


def reset_login_attempts(ip: str) -> None:
    key = f"login_ip_{ip}"
    conn = get_connection()
    try:
        conn.execute("DELETE FROM rate_limit_counters WHERE key=? AND window_type='login'", (key,))
        conn.commit()
    finally:
        conn.close()


# ── Session management ────────────────────────────────────────────────────────

def create_session(user_id: str, ip_address: str, user_agent: str) -> str:
    """Create a new session, lazy-clean expired sessions, return session_id."""
    session_id = secrets.token_hex(32)
    now = _now()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=_SESSION_TTL_HOURS)).isoformat()

    conn = get_connection()
    try:
        # Lazy cleanup of expired sessions
        conn.execute("DELETE FROM user_sessions WHERE expires_at < ?", (now,))
        conn.execute(
            """INSERT INTO user_sessions
               (session_id, user_id, created_at, expires_at, ip_address, user_agent, mfa_verified)
               VALUES (?,?,?,?,?,?,0)""",
            (session_id, user_id, now, expires_at, ip_address, user_agent),
        )
        conn.commit()
    finally:
        conn.close()
    return session_id


def resolve_session(session_id: str) -> dict | None:
    """Return session row or None. Deletes expired session if found."""
    if not session_id:
        return None
    now = _now()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM user_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        if row["expires_at"] < now:
            conn.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            return None
        return dict(row)
    finally:
        conn.close()


def delete_session(session_id: str) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def delete_all_sessions_for_user(user_id: str, except_session: str | None = None) -> None:
    conn = get_connection()
    try:
        if except_session:
            conn.execute(
                "DELETE FROM user_sessions WHERE user_id = ? AND session_id != ?",
                (user_id, except_session),
            )
        else:
            conn.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
