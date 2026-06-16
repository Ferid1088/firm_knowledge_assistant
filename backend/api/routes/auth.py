"""Auth endpoints: /api/auth/status, /login, /logout, /me, /change-password."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from backend.services import iam, audit
from backend.services.auth import (
    check_login_rate_limit, increment_login_attempts, reset_login_attempts,
    create_session, delete_session, delete_all_sessions_for_user,
    verify_password, hash_password, resolve_session,
)

router = APIRouter()

_SESSION_COOKIE = "rag_session"
_SESSION_MAX_AGE = 8 * 3600  # 8 hours


def _user_response(user: iam.User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "role_id": user.role_id,
        "role_name": user.role_name,
        "department_id": user.department_id,
        "permissions": user.permissions,
        "must_change_password": user.must_change_password,
        "allowed_doc_type_ids": user.allowed_doc_type_ids,  # None = all types
    }


@router.get("/api/auth/status")
def auth_status(request: Request):
    """Public endpoint. Frontend middleware calls this on every page load."""
    if iam.count_users() == 0:
        return {"setup_required": True}
    session_id = request.cookies.get(_SESSION_COOKIE, "")
    session = resolve_session(session_id)
    if not session:
        return {"authenticated": False}
    user = iam.get_user(session["user_id"])
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "user": _user_response(user)}


class SetupRequest(BaseModel):
    username: str
    password: str


@router.post("/api/auth/setup")
def setup(req: SetupRequest, request: Request, response: Response):
    """First-run only: create the first superadmin. Returns 409 if users already exist."""
    if iam.count_users() > 0:
        raise HTTPException(status_code=409, detail="Setup already complete")
    if not req.username.strip():
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    iam.init_seed_data()
    pw_hash = hash_password(req.password)
    user = iam.create_user(
        username=req.username.strip(),
        password_hash=pw_hash,
        name=req.username.strip().title(),
        department_id="dept-tech",
        role_id="superadmin",
    )
    audit.log_action(
        user_id=user.id,
        conversation_id=None,
        action="admin_created_via_wizard",
        resource_type="auth",
        decision="allow",
        ip_address=request.client.host if request.client else "unknown",
    )
    session_id = create_session(user.id, request.client.host if request.client else "unknown",
                                request.headers.get("user-agent", ""))
    response.set_cookie(key=_SESSION_COOKIE, value=session_id, httponly=True,
                        samesite="strict", path="/", max_age=_SESSION_MAX_AGE)
    return _user_response(user)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/api/auth/login")
def login(req: LoginRequest, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"

    # Rate limit check BEFORE any credential lookup
    try:
        check_login_rate_limit(ip)
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))

    # Always look up and always verify — prevents timing oracle
    raw = iam.get_user_by_username(req.username)
    stored_hash = raw["password_hash"] if raw else ""
    password_ok = verify_password(req.password, stored_hash)

    if raw is None or not password_ok or not raw["is_active"]:
        increment_login_attempts(ip)
        audit.log_action(
            user_id=raw["id"] if raw else "unknown",
            conversation_id=None,
            action="login_failed",
            resource_type="auth",
            decision="deny",
            ip_address=ip,
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create session, reset rate limit counter on success
    session_id = create_session(
        user_id=raw["id"],
        ip_address=ip,
        user_agent=request.headers.get("user-agent", ""),
    )
    reset_login_attempts(ip)

    audit.log_action(
        user_id=raw["id"],
        conversation_id=None,
        action="login_success",
        resource_type="auth",
        decision="allow",
        ip_address=ip,
    )

    response.set_cookie(
        key=_SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="strict",
        path="/",
        max_age=_SESSION_MAX_AGE,
    )
    user = iam.get_user(raw["id"])
    return _user_response(user)


@router.post("/api/auth/logout")
def logout(request: Request, response: Response):
    session_id = request.cookies.get(_SESSION_COOKIE, "")
    session = resolve_session(session_id)
    if session:
        audit.log_action(
            user_id=session["user_id"],
            conversation_id=None,
            action="logout",
            resource_type="auth",
            decision="allow",
            ip_address=request.client.host if request.client else "unknown",
        )
        delete_session(session_id)
    response.delete_cookie(_SESSION_COOKIE)
    return {"ok": True}


@router.get("/api/auth/me")
def me(request: Request):
    session_id = request.cookies.get(_SESSION_COOKIE, "")
    session = resolve_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = iam.get_user(session["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _user_response(user)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/api/auth/change-password")
def change_password(req: ChangePasswordRequest, request: Request):
    session_id = request.cookies.get(_SESSION_COOKIE, "")
    session = resolve_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    raw = iam.get_user_by_username(iam.get_user(session["user_id"]).username)
    if not raw or not verify_password(req.current_password, raw["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    from backend.database import get_connection
    from datetime import datetime, timezone
    new_hash = hash_password(req.new_password)
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET password_hash=?, must_change_password=0, updated_at=? WHERE id=?",
            (new_hash, datetime.now(timezone.utc).isoformat(), raw["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    delete_all_sessions_for_user(raw["id"], except_session=session_id)
    audit.log_action(raw["id"], None, "password_changed", resource_type="auth", decision="allow")
    return {"ok": True}
