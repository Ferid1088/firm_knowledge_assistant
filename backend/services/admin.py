"""Admin CRUD: users, departments, roles, permissions, audit log, system stats."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from backend.database import get_connection
from backend.services.iam import _permissions_for_role, get_user


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Users ─────────────────────────────────────────────────────────────────────

def list_users_admin(dept_id: str | None = None, role_id: str | None = None,
                     active_only: bool | None = None, page: int = 1, per_page: int = 50) -> dict:
    clauses = []
    params: list = []
    if dept_id:
        clauses.append("u.department_id = ?")
        params.append(dept_id)
    if role_id:
        clauses.append("u.role_id = ?")
        params.append(role_id)
    if active_only is not None:
        clauses.append("u.is_active = ?")
        params.append(1 if active_only else 0)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    conn = get_connection()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM users u {where}", params
        ).fetchone()[0]
        offset = (page - 1) * per_page
        rows = conn.execute(
            f"SELECT u.*, r.name AS role_name FROM users u "
            f"JOIN roles r ON r.id = u.role_id {where} "
            f"ORDER BY u.name LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()
        items = [
            {k: v for k, v in dict(r).items() if k not in ("password_hash", "mfa_secret")}
            for r in rows
        ]
        return {"total": total, "page": page, "per_page": per_page, "items": items}
    finally:
        conn.close()


def get_user_admin(user_id: str) -> dict:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT u.*, r.name AS role_name FROM users u JOIN roles r ON r.id = u.role_id WHERE u.id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise ValueError("user not found")
        d = {k: v for k, v in dict(row).items() if k not in ("password_hash", "mfa_secret")}
        d["permissions"] = _permissions_for_role(row["role_id"], conn)
        return d
    finally:
        conn.close()


def create_user_admin(username: str, password: str, name: str,
                      department_id: str, role_id: str) -> dict:
    from backend.services.auth import hash_password
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    pw_hash = hash_password(password)
    user_id = str(uuid.uuid4())
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO users (id, username, password_hash, name, department_id, role_id,
               is_active, mfa_enabled, mfa_secret, created_at, updated_at)
               VALUES (?,?,?,?,?,?,1,0,NULL,?,?)""",
            (user_id, username, pw_hash, name, department_id, role_id, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return get_user_admin(user_id)


def update_user_admin(user_id: str, **fields) -> dict:
    allowed = {"name", "department_id", "role_id", "is_active"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_user_admin(user_id)
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE users SET {set_clause} WHERE id = ?",
            list(updates.values()) + [user_id],
        )
        conn.commit()
    finally:
        conn.close()
    return get_user_admin(user_id)


def reset_password_admin(user_id: str, new_password: str) -> None:
    from backend.services.auth import hash_password, delete_all_sessions_for_user
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters")
    pw_hash = hash_password(new_password)
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
            (pw_hash, _now(), user_id),
        )
        conn.commit()
    finally:
        conn.close()
    delete_all_sessions_for_user(user_id)


def deactivate_user_admin(user_id: str) -> dict:
    from backend.services.auth import delete_all_sessions_for_user
    delete_all_sessions_for_user(user_id)
    return update_user_admin(user_id, is_active=0)


# ── Departments ───────────────────────────────────────────────────────────────

def list_departments_admin() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM departments ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_department_admin(name: str, code: str) -> dict:
    dept_id = "dept-" + code.lower().replace("_", "-")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO departments (id, name, code, status, created_at) VALUES (?,?,?,'active',?)",
            (dept_id, name, code.upper(), now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM departments WHERE id = ?", (dept_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_department_admin(dept_id: str, name: str | None = None, status: str | None = None) -> dict:
    if status == "archived":
        conn = get_connection()
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM users WHERE department_id = ? AND is_active = 1", (dept_id,)
            ).fetchone()[0]
            if count > 0:
                raise ValueError(f"Cannot archive: {count} active user(s) in this department")
        finally:
            conn.close()

    updates: dict = {}
    if name is not None:
        updates["name"] = name
    if status is not None:
        updates["status"] = status
    conn = get_connection()
    try:
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE departments SET {set_clause} WHERE id = ?",
                list(updates.values()) + [dept_id],
            )
            conn.commit()
        row = conn.execute("SELECT * FROM departments WHERE id = ?", (dept_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


# ── Roles ─────────────────────────────────────────────────────────────────────

def list_roles_admin() -> list[dict]:
    conn = get_connection()
    try:
        roles = conn.execute("SELECT * FROM roles ORDER BY name").fetchall()
        result = []
        for r in roles:
            rd = dict(r)
            rd["permissions"] = _permissions_for_role(r["id"], conn)
            result.append(rd)
        return result
    finally:
        conn.close()


def create_role_admin(name: str, description: str = "") -> dict:
    role_id = "role-" + name.lower().replace(" ", "-")
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO roles (id, name, description, is_system, created_at) VALUES (?,?,?,0,?)",
            (role_id, name, description, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
        rd = dict(row)
        rd["permissions"] = []
        return rd
    finally:
        conn.close()


def update_role_admin(role_id: str, name: str | None = None, description: str | None = None) -> dict:
    updates: dict = {}
    if name is not None:
        updates["name"] = name
    if description is not None:
        updates["description"] = description
    conn = get_connection()
    try:
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE roles SET {set_clause} WHERE id = ?",
                list(updates.values()) + [role_id],
            )
            conn.commit()
        row = conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
        if row is None:
            raise ValueError("Role not found")
        rd = dict(row)
        rd["permissions"] = _permissions_for_role(role_id, conn)
        return rd
    finally:
        conn.close()


def delete_role_admin(role_id: str) -> None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT is_system FROM roles WHERE id = ?", (role_id,)).fetchone()
        if row is None:
            raise ValueError("Role not found")
        if row[0]:
            raise ValueError("Cannot delete a system role")
        user_count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role_id = ?", (role_id,)
        ).fetchone()[0]
        if user_count > 0:
            raise ValueError(f"Cannot delete: {user_count} user(s) have this role")
        conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
        conn.commit()
    finally:
        conn.close()


def set_role_permissions_admin(role_id: str, permission_ids: list[str]) -> dict:
    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM roles WHERE id = ?", (role_id,)).fetchone() is None:
            raise ValueError("Role not found")
        conn.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
        for perm_id in permission_ids:
            conn.execute(
                "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?,?)",
                (role_id, perm_id),
            )
        conn.commit()
    finally:
        conn.close()
    return update_role_admin(role_id)


# ── Permissions ───────────────────────────────────────────────────────────────

def list_permissions_admin() -> list[dict]:
    conn = get_connection()
    try:
        return [
            dict(r) for r in conn.execute(
                "SELECT * FROM permissions ORDER BY resource, action"
            ).fetchall()
        ]
    finally:
        conn.close()


# ── Audit log ─────────────────────────────────────────────────────────────────

def list_audit_log(user_id: str | None = None, action: str | None = None,
                   resource_type: str | None = None, date_from: str | None = None,
                   date_to: str | None = None, page: int = 1, per_page: int = 50) -> dict:
    clauses = []
    params: list = []
    if user_id:
        clauses.append("a.user_id = ?")
        params.append(user_id)
    if action:
        clauses.append("a.action = ?")
        params.append(action)
    if resource_type:
        clauses.append("a.resource_type = ?")
        params.append(resource_type)
    if date_from:
        clauses.append("a.created_at >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("a.created_at <= ?")
        params.append(date_to)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    conn = get_connection()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM audit_log a {where}", params
        ).fetchone()[0]
        offset = (page - 1) * per_page
        rows = conn.execute(
            f"""SELECT a.*, u.username FROM audit_log a
                LEFT JOIN users u ON u.id = a.user_id {where}
                ORDER BY a.created_at DESC LIMIT ? OFFSET ?""",
            params + [per_page, offset],
        ).fetchall()
        return {"total": total, "page": page, "per_page": per_page, "items": [dict(r) for r in rows]}
    finally:
        conn.close()


# ── System stats ──────────────────────────────────────────────────────────────

def system_stats() -> dict:
    from pathlib import Path
    from backend.config import QDRANT_DIR

    conn = get_connection()
    try:
        active_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_active=1").fetchone()[0]
    finally:
        conn.close()

    qdrant_points = 0
    total_docs = 0
    try:
        from backend.graph.utils import get_collection
        client, collection_name = get_collection()
        info = client.get_collection(collection_name=collection_name)
        qdrant_points = info.points_count or 0
    except Exception:
        pass

    storage_bytes = 0
    qdrant_path = Path(QDRANT_DIR)
    if qdrant_path.exists():
        storage_bytes = sum(f.stat().st_size for f in qdrant_path.rglob("*") if f.is_file())

    return {
        "active_users": active_users,
        "total_docs_indexed": total_docs,
        "qdrant_point_count": qdrant_points,
        "storage_bytes": storage_bytes,
    }
