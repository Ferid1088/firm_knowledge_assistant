"""Admin panel endpoints: /api/admin/*. All require admin_panel:access permission."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from backend.services import admin as admin_svc
from backend.services.iam import User
from backend.services.auth import resolve_session
from backend.services import iam

router = APIRouter(prefix="/api/admin")


def _get_admin_user(request: Request) -> User:
    """Resolve session and verify admin_panel:access permission."""
    session_id = request.cookies.get("rag_session", "")
    session = resolve_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = iam.get_user(session["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if "admin_panel:access" not in user.permissions:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── Users ──────────────────────────────────────────────────────────────────────

@router.get("/users")
def list_users(request: Request, dept_id: Optional[str] = None, role_id: Optional[str] = None,
               active_only: Optional[bool] = None, page: int = 1):
    _get_admin_user(request)
    return admin_svc.list_users_admin(dept_id=dept_id, role_id=role_id, active_only=active_only, page=page)


class CreateUserRequest(BaseModel):
    username: str
    password: str
    name: str
    department_id: str
    role_id: str


@router.post("/users", status_code=201)
def create_user(req: CreateUserRequest, request: Request):
    _get_admin_user(request)
    try:
        return admin_svc.create_user_admin(req.username, req.password, req.name, req.department_id, req.role_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/users/{user_id}")
def get_user(user_id: str, request: Request):
    _get_admin_user(request)
    try:
        return admin_svc.get_user_admin(user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    department_id: Optional[str] = None
    role_id: Optional[str] = None
    is_active: Optional[int] = None


@router.patch("/users/{user_id}")
def update_user(user_id: str, req: UpdateUserRequest, request: Request):
    _get_admin_user(request)
    return admin_svc.update_user_admin(user_id, **req.model_dump(exclude_none=True))


class ResetPasswordRequest(BaseModel):
    new_password: str


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: str, req: ResetPasswordRequest, request: Request):
    _get_admin_user(request)
    try:
        admin_svc.reset_password_admin(user_id, req.new_password)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/users/{user_id}")
def deactivate_user(user_id: str, request: Request):
    _get_admin_user(request)
    return admin_svc.deactivate_user_admin(user_id)


# ── Departments ────────────────────────────────────────────────────────────────

@router.get("/departments")
def list_departments(request: Request):
    _get_admin_user(request)
    return admin_svc.list_departments_admin()


class CreateDeptRequest(BaseModel):
    name: str
    code: str


@router.post("/departments", status_code=201)
def create_department(req: CreateDeptRequest, request: Request):
    _get_admin_user(request)
    try:
        return admin_svc.create_department_admin(req.name, req.code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class UpdateDeptRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None


@router.patch("/departments/{dept_id}")
def update_department(dept_id: str, req: UpdateDeptRequest, request: Request):
    _get_admin_user(request)
    try:
        return admin_svc.update_department_admin(dept_id, req.name, req.status)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ── Roles ──────────────────────────────────────────────────────────────────────

@router.get("/roles")
def list_roles(request: Request):
    _get_admin_user(request)
    return admin_svc.list_roles_admin()


class CreateRoleRequest(BaseModel):
    name: str
    description: str = ""


@router.post("/roles", status_code=201)
def create_role(req: CreateRoleRequest, request: Request):
    _get_admin_user(request)
    try:
        return admin_svc.create_role_admin(req.name, req.description)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class UpdateRoleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


@router.patch("/roles/{role_id}")
def update_role(role_id: str, req: UpdateRoleRequest, request: Request):
    _get_admin_user(request)
    return admin_svc.update_role_admin(role_id, req.name, req.description)


@router.delete("/roles/{role_id}")
def delete_role(role_id: str, request: Request):
    _get_admin_user(request)
    try:
        admin_svc.delete_role_admin(role_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class SetPermissionsRequest(BaseModel):
    permission_ids: list[str]


@router.put("/roles/{role_id}/permissions")
def set_role_permissions(role_id: str, req: SetPermissionsRequest, request: Request):
    _get_admin_user(request)
    try:
        return admin_svc.set_role_permissions_admin(role_id, req.permission_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Document types ─────────────────────────────────────────────────────────────

@router.get("/doc-types")
def list_doc_types(request: Request, active_only: bool = False):
    _get_admin_user(request)
    return admin_svc.list_doc_types_admin(active_only=active_only)


class CreateDocTypeRequest(BaseModel):
    name: str
    description: str = ""


@router.post("/doc-types", status_code=201)
def create_doc_type(req: CreateDocTypeRequest, request: Request):
    _get_admin_user(request)
    try:
        return admin_svc.create_doc_type_admin(req.name, req.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class UpdateDocTypeRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


@router.patch("/doc-types/{dt_id}")
def update_doc_type(dt_id: str, req: UpdateDocTypeRequest, request: Request):
    _get_admin_user(request)
    try:
        return admin_svc.update_doc_type_admin(dt_id, req.name, req.description, req.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── User doc type permissions ───────────────────────────────────────────────────

@router.get("/users/{user_id}/doc-type-permissions")
def get_user_doc_type_perms(user_id: str, request: Request):
    _get_admin_user(request)
    dt_ids = admin_svc.get_user_doc_type_ids(user_id)
    return {"user_id": user_id, "allowed_doc_type_ids": dt_ids}


class SetDocTypePermsRequest(BaseModel):
    doc_type_ids: list[str]


@router.put("/users/{user_id}/doc-type-permissions")
def set_user_doc_type_perms(user_id: str, req: SetDocTypePermsRequest, request: Request):
    _get_admin_user(request)
    return admin_svc.set_user_doc_type_permissions(user_id, req.doc_type_ids)


# ── Permissions ────────────────────────────────────────────────────────────────

@router.get("/permissions")
def list_permissions(request: Request):
    _get_admin_user(request)
    return admin_svc.list_permissions_admin()


# ── Audit log ──────────────────────────────────────────────────────────────────

@router.get("/audit-log")
def audit_log(request: Request, user_id: Optional[str] = None, action: Optional[str] = None,
              resource_type: Optional[str] = None, date_from: Optional[str] = None,
              date_to: Optional[str] = None, page: int = 1):
    _get_admin_user(request)
    return admin_svc.list_audit_log(
        user_id=user_id, action=action, resource_type=resource_type,
        date_from=date_from, date_to=date_to, page=page,
    )


# ── System stats ───────────────────────────────────────────────────────────────

@router.get("/stats")
def stats(request: Request):
    _get_admin_user(request)
    return admin_svc.system_stats()
