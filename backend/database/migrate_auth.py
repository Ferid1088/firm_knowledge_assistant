"""One-time migration: rename old users/departments, recreate with auth columns.

Run: python -m backend.database.migrate_auth

Safe to re-run: checks whether migration is already done.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.database import get_connection


def already_migrated(conn) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='roles'"
    ).fetchone()
    return row is not None


def run_migration() -> None:
    conn = get_connection()
    try:
        if already_migrated(conn):
            print("Migration already applied — roles table exists. Exiting.")
            return

        print("Starting auth migration…")
        conn.execute("PRAGMA foreign_keys = OFF")

        # ── 1. Add new nullable columns to audit_log ───────────────────────────
        existing_audit_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(audit_log)").fetchall()
        }
        for col, typedef in [
            ("resource_type", "TEXT"),
            ("decision", "TEXT"),
            ("ip_address", "TEXT"),
        ]:
            if col not in existing_audit_cols:
                conn.execute(f"ALTER TABLE audit_log ADD COLUMN {col} {typedef}")
        print("  audit_log columns added.")

        # ── 2. Recreate departments with code + status ────────────────────────
        conn.execute("ALTER TABLE departments RENAME TO departments_old")
        conn.execute("""
            CREATE TABLE departments (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                code       TEXT NOT NULL UNIQUE,
                status     TEXT NOT NULL DEFAULT 'active'
                               CHECK (status IN ('active', 'archived')),
                created_at TEXT NOT NULL
            )
        """)
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rows = conn.execute("SELECT id, name FROM departments_old").fetchall()
        for r in rows:
            code = r["id"].removeprefix("dept-").upper().replace("-", "_")  # "dept-hr" -> "HR", "dept-engineering-backend" -> "ENGINEERING_BACKEND"
            conn.execute(
                "INSERT INTO departments (id, name, code, status, created_at) VALUES (?,?,?,'active',?)",
                (r["id"], r["name"], code, now),
            )
        print(f"  departments migrated ({len(rows)} rows).")

        # ── 3. Create roles + permissions + role_permissions ──────────────────
        conn.execute("""
            CREATE TABLE roles (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL UNIQUE,
                description TEXT,
                is_system   INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE permissions (
                id          TEXT PRIMARY KEY,
                resource    TEXT NOT NULL,
                action      TEXT NOT NULL,
                description TEXT,
                UNIQUE (resource, action)
            )
        """)
        conn.execute("""
            CREATE TABLE role_permissions (
                role_id       TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                permission_id TEXT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
                PRIMARY KEY (role_id, permission_id)
            )
        """)
        print("  roles/permissions tables created.")

        # Insert system roles before migrating users (FK references)
        import datetime as _dt
        _now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        conn.execute("""
            INSERT OR IGNORE INTO roles (id, name, description, is_system, created_at)
            VALUES ('superadmin', 'Super Admin', 'Full access including admin panel', 1, ?)
        """, (_now,))
        conn.execute("""
            INSERT OR IGNORE INTO roles (id, name, description, is_system, created_at)
            VALUES ('member', 'Member', 'Standard user', 1, ?)
        """, (_now,))
        print("  system roles inserted.")

        # ── 4. Recreate users with auth columns ───────────────────────────────
        conn.execute("ALTER TABLE users RENAME TO users_old")
        conn.execute("""
            CREATE TABLE users (
                id            TEXT PRIMARY KEY,
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL DEFAULT '',
                name          TEXT NOT NULL,
                department_id TEXT NOT NULL REFERENCES departments(id),
                role_id       TEXT NOT NULL REFERENCES roles(id),
                is_active     INTEGER NOT NULL DEFAULT 1,
                mfa_enabled   INTEGER NOT NULL DEFAULT 0,
                mfa_secret    TEXT,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            )
        """)
        old_users = conn.execute("SELECT * FROM users_old").fetchall()
        for u in old_users:
            role_id = "superadmin" if u["role"] in ("admin", "superadmin") else "member"
            username = u["id"].replace("user-", "").replace("-", "_")
            conn.execute(
                """INSERT INTO users
                   (id, username, password_hash, name, department_id, role_id,
                    is_active, mfa_enabled, mfa_secret, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,1,0,NULL,?,?)""",
                (u["id"], username, "", u["name"], u["department_id"], role_id, now, now),
            )
        print(f"  users migrated ({len(old_users)} rows).")

        # ── 5. Recreate rate_limit_counters without FK (allow IP keys) ────────
        has_rl = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rate_limit_counters'"
        ).fetchone()
        if has_rl:
            conn.execute("ALTER TABLE rate_limit_counters RENAME TO rate_limit_counters_old")
            conn.execute("""
                CREATE TABLE rate_limit_counters (
                    key          TEXT NOT NULL,
                    window_type  TEXT NOT NULL,
                    window_start TEXT NOT NULL,
                    count        INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (key, window_type, window_start)
                )
            """)
            old_rl = conn.execute("SELECT * FROM rate_limit_counters_old").fetchall()
            for r in old_rl:
                conn.execute(
                    "INSERT INTO rate_limit_counters (key, window_type, window_start, count) VALUES (?,?,?,?)",
                    (r["user_id"], r["window_type"], r["window_start"], r["count"]),
                )
            print(f"  rate_limit_counters migrated ({len(old_rl)} rows).")
            conn.execute("DROP TABLE rate_limit_counters_old")
        else:
            conn.execute("""
                CREATE TABLE rate_limit_counters (
                    key          TEXT NOT NULL,
                    window_type  TEXT NOT NULL,
                    window_start TEXT NOT NULL,
                    count        INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (key, window_type, window_start)
                )
            """)
            print("  rate_limit_counters created (was absent).")

        # ── 6. Create user_sessions ───────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id   TEXT PRIMARY KEY,
                user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at   TEXT NOT NULL,
                expires_at   TEXT NOT NULL,
                ip_address   TEXT NOT NULL,
                user_agent   TEXT NOT NULL,
                mfa_verified INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at)"
        )
        print("  user_sessions table created.")

        # ── 7. Clean up: drop only tables that are truly obsolete ─────────────
        # departments_old and users_old are kept for safety — drop manually after
        # verifying production data is intact. agent_sessions is replaced by user_sessions.
        conn.execute("DROP TABLE IF EXISTS agent_sessions")

        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()
        print("Migration complete.")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
