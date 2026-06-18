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
    """List users with optional filters by department, role, or active status."""
    _get_admin_user(request)
    return admin_svc.list_users_admin(dept_id=dept_id, role_id=role_id, active_only=active_only, page=page)


class CreateUserRequest(BaseModel):
    """Request body for POST /api/admin/users."""

    username: str
    password: str
    name: str
    department_id: str
    role_id: str


@router.post("/users", status_code=201)
def create_user(req: CreateUserRequest, request: Request):
    """Create a new user account; hashing is done in the service layer."""
    _get_admin_user(request)
    try:
        return admin_svc.create_user_admin(req.username, req.password, req.name, req.department_id, req.role_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/users/{user_id}")
def get_user(user_id: str, request: Request):
    """Fetch a single user by ID (404 if not found)."""
    _get_admin_user(request)
    try:
        return admin_svc.get_user_admin(user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class UpdateUserRequest(BaseModel):
    """Request body for PATCH /api/admin/users/{id}."""

    name: Optional[str] = None
    department_id: Optional[str] = None
    role_id: Optional[str] = None
    is_active: Optional[int] = None


@router.patch("/users/{user_id}")
def update_user(user_id: str, req: UpdateUserRequest, request: Request):
    """Partial update of user fields (name, department, role, active status)."""
    _get_admin_user(request)
    return admin_svc.update_user_admin(user_id, **req.model_dump(exclude_none=True))


class ResetPasswordRequest(BaseModel):
    """Request body for POST /api/admin/users/{id}/reset-password."""

    new_password: str


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: str, req: ResetPasswordRequest, request: Request):
    """Admin-initiated password reset; sets must_change_password=True on the account."""
    _get_admin_user(request)
    try:
        admin_svc.reset_password_admin(user_id, req.new_password)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/users/{user_id}")
def deactivate_user(user_id: str, request: Request):
    """Deactivate a user account (soft disable — does not delete the row). Superadmins cannot be deactivated."""
    _get_admin_user(request)
    try:
        return admin_svc.deactivate_user_admin(user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Departments ────────────────────────────────────────────────────────────────

@router.get("/departments")
def list_departments(request: Request):
    """List all departments (used to populate dropdowns in the admin panel and upload modal)."""
    _get_admin_user(request)
    return admin_svc.list_departments_admin()


class CreateDeptRequest(BaseModel):
    """Request body for POST /api/admin/departments."""

    name: str
    code: str


@router.post("/departments", status_code=201)
def create_department(req: CreateDeptRequest, request: Request):
    """Create a new department; code must be unique."""
    _get_admin_user(request)
    try:
        return admin_svc.create_department_admin(req.name, req.code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class UpdateDeptRequest(BaseModel):
    """Request body for PATCH /api/admin/departments/{id}."""

    name: Optional[str] = None
    status: Optional[str] = None


@router.patch("/departments/{dept_id}")
def update_department(dept_id: str, req: UpdateDeptRequest, request: Request):
    """Update department name or status (active/archived)."""
    _get_admin_user(request)
    try:
        return admin_svc.update_department_admin(dept_id, req.name, req.status)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ── Roles ──────────────────────────────────────────────────────────────────────

@router.get("/roles")
def list_roles(request: Request):
    """List all roles (system + custom) with their permission sets."""
    _get_admin_user(request)
    return admin_svc.list_roles_admin()


class CreateRoleRequest(BaseModel):
    """Request body for POST /api/admin/roles."""

    name: str
    description: str = ""


@router.post("/roles", status_code=201)
def create_role(req: CreateRoleRequest, request: Request):
    """Create a custom role; permissions are assigned via PUT /roles/{id}/permissions."""
    _get_admin_user(request)
    try:
        return admin_svc.create_role_admin(req.name, req.description)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class UpdateRoleRequest(BaseModel):
    """Request body for PATCH /api/admin/roles/{id}."""

    name: Optional[str] = None
    description: Optional[str] = None


@router.patch("/roles/{role_id}")
def update_role(role_id: str, req: UpdateRoleRequest, request: Request):
    """Update role name or description (system roles cannot be renamed)."""
    _get_admin_user(request)
    return admin_svc.update_role_admin(role_id, req.name, req.description)


@router.delete("/roles/{role_id}")
def delete_role(role_id: str, request: Request):
    """Delete a custom role; raises 400 if it is a system role or still assigned."""
    _get_admin_user(request)
    try:
        admin_svc.delete_role_admin(role_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class SetPermissionsRequest(BaseModel):
    """Request body for PUT /api/admin/roles/{id}/permissions."""

    permission_ids: list[str]


@router.put("/roles/{role_id}/permissions")
def set_role_permissions(role_id: str, req: SetPermissionsRequest, request: Request):
    """Replace the full permission set for a role (idempotent PUT semantics)."""
    _get_admin_user(request)
    try:
        return admin_svc.set_role_permissions_admin(role_id, req.permission_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Document types ─────────────────────────────────────────────────────────────

@router.get("/doc-types")
def list_doc_types(request: Request, active_only: bool = False):
    """List document types; pass active_only=true to exclude archived types."""
    _get_admin_user(request)
    return admin_svc.list_doc_types_admin(active_only=active_only)


class CreateDocTypeRequest(BaseModel):
    """Request body for POST /api/admin/doc-types."""

    name: str
    description: str = ""


@router.post("/doc-types", status_code=201)
def create_doc_type(req: CreateDocTypeRequest, request: Request):
    """Create a new document type visible to users during upload."""
    _get_admin_user(request)
    try:
        return admin_svc.create_doc_type_admin(req.name, req.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class UpdateDocTypeRequest(BaseModel):
    """Request body for PATCH /api/admin/doc-types/{id}."""

    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


@router.patch("/doc-types/{dt_id}")
def update_doc_type(dt_id: str, req: UpdateDocTypeRequest, request: Request):
    """Update doc type name, description, or status (active/archived)."""
    _get_admin_user(request)
    try:
        return admin_svc.update_doc_type_admin(dt_id, req.name, req.description, req.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── User doc type permissions ───────────────────────────────────────────────────

@router.get("/users/{user_id}/doc-type-permissions")
def get_user_doc_type_perms(user_id: str, request: Request):
    """Return the list of doc_type_ids the user may access (null = all types allowed)."""
    _get_admin_user(request)
    dt_ids = admin_svc.get_user_doc_type_ids(user_id)
    return {"user_id": user_id, "allowed_doc_type_ids": dt_ids}


class SetDocTypePermsRequest(BaseModel):
    """Request body for PUT /api/admin/users/{id}/doc-type-permissions."""

    doc_type_ids: list[str]


@router.put("/users/{user_id}/doc-type-permissions")
def set_user_doc_type_perms(user_id: str, req: SetDocTypePermsRequest, request: Request):
    """Replace the user's doc-type access list (empty list = no access to any type)."""
    _get_admin_user(request)
    return admin_svc.set_user_doc_type_permissions(user_id, req.doc_type_ids)


# ── User department permissions ────────────────────────────────────────────────

@router.get("/users/{user_id}/department-permissions")
def get_user_dept_perms(user_id: str, request: Request):
    """Return the list of department_ids the user may access (null = all departments allowed)."""
    _get_admin_user(request)
    dept_ids = admin_svc.get_user_department_ids(user_id)
    return {"user_id": user_id, "allowed_department_ids": dept_ids}


class SetDeptPermsRequest(BaseModel):
    """Request body for PUT /api/admin/users/{id}/department-permissions."""

    department_ids: list[str]


@router.put("/users/{user_id}/department-permissions")
def set_user_dept_perms(user_id: str, req: SetDeptPermsRequest, request: Request):
    """Replace the user's department access list (empty list = unrestricted)."""
    _get_admin_user(request)
    return admin_svc.set_user_department_permissions(user_id, req.department_ids)


# ── Permissions ────────────────────────────────────────────────────────────────

@router.get("/permissions")
def list_permissions(request: Request):
    """List all available permission entries (used to build the role-permission editor)."""
    _get_admin_user(request)
    return admin_svc.list_permissions_admin()


# ── Audit log ──────────────────────────────────────────────────────────────────

@router.get("/audit-log")
def audit_log(request: Request, user_id: Optional[str] = None, action: Optional[str] = None,
              resource_type: Optional[str] = None, date_from: Optional[str] = None,
              date_to: Optional[str] = None, page: int = 1):
    """Return paginated audit log entries with optional filters."""
    _get_admin_user(request)
    return admin_svc.list_audit_log(
        user_id=user_id, action=action, resource_type=resource_type,
        date_from=date_from, date_to=date_to, page=page,
    )


# ── System stats ───────────────────────────────────────────────────────────────

@router.get("/stats")
def stats(request: Request):
    """Return system-wide statistics (users, documents, chunks, cache, rate limits)."""
    _get_admin_user(request)
    return admin_svc.system_stats()
