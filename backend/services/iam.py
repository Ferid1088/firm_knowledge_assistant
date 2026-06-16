"""IAM: roles, permissions, departments, users, and access-control checks."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.database import get_connection
from backend.config import SEED_DEPARTMENTS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class User:
    id: str
    username: str
    name: str
    department_id: str
    role_id: str
    role_name: str
    permissions: list[str] = field(default_factory=list)

    @property
    def is_superadmin(self) -> bool:
        return self.role_id == "superadmin"


# ── Seed data ────────────────────────────────────────────────────────────────

_ROLES = [
    ("superadmin", "Super Admin", "Full access including admin panel", 1),
    ("member",     "Member",      "Standard user",                     1),
]

_PERMISSIONS = [
    ("perm_conv_read_own",  "conversations", "read_own",  "Read own conversations"),
    ("perm_conv_create",    "conversations", "create",    "Create conversations"),
    ("perm_doc_read",       "documents",     "read",      "Read indexed documents"),
    ("perm_doc_upload",     "documents",     "upload",    "Upload documents"),
    ("perm_admin_access",   "admin_panel",   "access",    "Access admin panel"),
    ("perm_audit_view",     "audit",         "view",      "View audit log"),
]

_ROLE_PERMISSIONS = {
    "superadmin": [p[0] for p in _PERMISSIONS],
    "member": ["perm_conv_read_own", "perm_conv_create", "perm_doc_read", "perm_doc_upload"],
}


def init_seed_data() -> None:
    """Idempotently insert roles, permissions, departments on startup."""
    conn = get_connection()
    try:
        now = _now()
        for role_id, name, desc, is_system in _ROLES:
            conn.execute(
                "INSERT OR IGNORE INTO roles (id, name, description, is_system, created_at) VALUES (?,?,?,?,?)",
                (role_id, name, desc, is_system, now),
            )
        for perm_id, resource, action, desc in _PERMISSIONS:
            conn.execute(
                "INSERT OR IGNORE INTO permissions (id, resource, action, description) VALUES (?,?,?,?)",
                (perm_id, resource, action, desc),
            )
        for role_id, perm_ids in _ROLE_PERMISSIONS.items():
            for perm_id in perm_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?,?)",
                    (role_id, perm_id),
                )
        for dept_id, name, code in SEED_DEPARTMENTS:
            conn.execute(
                "INSERT OR IGNORE INTO departments (id, name, code, status, created_at) VALUES (?,?,?,'active',?)",
                (dept_id, name, code, now),
            )
        conn.commit()
    finally:
        conn.close()


# ── User helpers ─────────────────────────────────────────────────────────────

def _permissions_for_role(role_id: str, conn) -> list[str]:
    rows = conn.execute(
        """SELECT p.resource || ':' || p.action
           FROM permissions p
           JOIN role_permissions rp ON rp.permission_id = p.id
           WHERE rp.role_id = ?""",
        (role_id,),
    ).fetchall()
    return [r[0] for r in rows]


def get_user(user_id: str) -> User | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT u.*, r.name AS role_name FROM users u JOIN roles r ON r.id = u.role_id WHERE u.id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        perms = _permissions_for_role(row["role_id"], conn)
        return User(
            id=row["id"], username=row["username"], name=row["name"],
            department_id=row["department_id"], role_id=row["role_id"],
            role_name=row["role_name"], permissions=perms,
        )
    finally:
        conn.close()


def get_user_by_username(username: str) -> dict | None:
    """Return raw row dict including password_hash. Never return to API."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_users() -> list[User]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT u.*, r.name AS role_name FROM users u JOIN roles r ON r.id = u.role_id ORDER BY u.name"
        ).fetchall()
        result = []
        for row in rows:
            perms = _permissions_for_role(row["role_id"], conn)
            result.append(User(
                id=row["id"], username=row["username"], name=row["name"],
                department_id=row["department_id"], role_id=row["role_id"],
                role_name=row["role_name"], permissions=perms,
            ))
        return result
    finally:
        conn.close()


def list_departments() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM departments ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_user(username: str, password_hash: str, name: str, department_id: str, role_id: str) -> User:
    user_id = str(uuid.uuid4())
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO users (id, username, password_hash, name, department_id, role_id,
               is_active, mfa_enabled, mfa_secret, created_at, updated_at)
               VALUES (?,?,?,?,?,?,1,0,NULL,?,?)""",
            (user_id, username, password_hash, name, department_id, role_id, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return get_user(user_id)


def count_users() -> int:
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


# ── Access control ────────────────────────────────────────────────────────────

def can_access_conversation(user: User, conversation: dict, conn=None) -> bool:
    if conversation["owner_user_id"] == user.id:
        return True
    own_conn = conn is None
    conn = conn or get_connection()
    try:
        shared = conn.execute(
            "SELECT 1 FROM conversation_shares WHERE conversation_id = ? AND user_id = ?",
            (conversation["id"], user.id),
        ).fetchone()
        return shared is not None
    finally:
        if own_conn:
            conn.close()


def can_agent_act(user: User, action: str, conversation: dict | None = None) -> bool:
    if conversation is None:
        return True
    return conversation["owner_user_id"] == user.id
