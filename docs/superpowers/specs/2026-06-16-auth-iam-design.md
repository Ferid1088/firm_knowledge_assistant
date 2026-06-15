# Auth & IAM — Revised Design Spec
**Date:** 2026-06-16
**Status:** Approved for implementation
**Replaces:** `docs/Auth_flow.md`, `docs/Auth_db.md` (those remain as reference; this is the authoritative build spec)

---

## 0. Constraints (non-negotiable)

| Constraint | Decision |
|---|---|
| ORM | Raw `sqlite3` — no Tortoise ORM |
| Sessions / rate-limit store | SQLite only — no Redis |
| Session cleanup | Lazy on login — no APScheduler |
| New packages | `pyotp` added to `requirements.txt` but **not called** until Phase 2 |
| Air-gap | All logic local; no email, no external IdP, no TOTP cloud service |
| CLAUDE.md | No package installed without this spec authorising it |

**Only new package authorised by this spec: `pyotp`** (added now, used in Phase 2).

---

## 1. Data Model

### 1.1 Schema additions to `backend/database/schema.sql`

All tables use `CREATE TABLE IF NOT EXISTS` (idempotent, zero-migration approach).

#### New tables

```sql
CREATE TABLE IF NOT EXISTS roles (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT,
    is_system   INTEGER NOT NULL DEFAULT 0,  -- 1 = cannot be deleted
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS permissions (
    id          TEXT PRIMARY KEY,
    resource    TEXT NOT NULL,   -- 'conversations' | 'documents' | 'admin_panel' | 'audit'
    action      TEXT NOT NULL,   -- 'read_own' | 'upload' | 'access' | 'view' | 'create'
    description TEXT,
    UNIQUE (resource, action)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id TEXT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS user_sessions (
    session_id TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    user_agent TEXT NOT NULL,
    mfa_verified INTEGER NOT NULL DEFAULT 0   -- 0 = not yet; 1 = verified (Phase 2)
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id
    ON user_sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at
    ON user_sessions(expires_at);
```

#### Modified table: `users`

SQLite does not support `ALTER TABLE … ADD COLUMN` with constraints on existing NOT NULL columns, so the revised `users` DDL replaces the old one. The migration script (`scripts/migrate_auth.py`) renames the old table, recreates it, and copies existing rows with safe defaults.

```sql
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,          -- login credential
    password_hash TEXT NOT NULL DEFAULT '',      -- pbkdf2_sha256$salt$hash; '' = must set password
    name          TEXT NOT NULL,                 -- display name
    department_id TEXT NOT NULL REFERENCES departments(id),
    role_id       TEXT NOT NULL REFERENCES roles(id),
    is_active     INTEGER NOT NULL DEFAULT 1,    -- 0 = deactivated (cannot log in)
    mfa_enabled   INTEGER NOT NULL DEFAULT 0,    -- Phase 2: 0 = off, 1 = TOTP required
    mfa_secret    TEXT,                          -- Phase 2: TOTP secret (AES-GCM encrypted)
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
-- NOTE: old `role` TEXT column (admin|member) is replaced by role_id FK
```

#### Modified table: `departments`

```sql
CREATE TABLE IF NOT EXISTS departments (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    code       TEXT NOT NULL UNIQUE,   -- short code e.g. 'HR', 'MGMT'
    status     TEXT NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL
);
```

#### Audit log — extended (existing table kept, new columns added via migration)

The existing `audit_log` table grows three columns for full commercial auditability:

```sql
-- Added via migration (ALTER TABLE IF column not exists pattern):
-- resource_type TEXT    -- 'auth' | 'conversation' | 'document' | 'admin' | 'iam'
-- decision      TEXT    -- 'allow' | 'deny'
-- ip_address    TEXT
-- Existing columns: id, user_id, conversation_id, action, details_json, created_at
```

Audit log rows are **never deleted** — no `DELETE` is ever issued on this table. The migration script backs it up before touching it.

---

### 1.2 Seed data (first run, idempotent)

Inserted by `iam.init_seed_data()` on startup (already called in `main.py`):

**Roles (system, undeletable):**
- `superadmin` — full access including admin panel
- `member` — standard user

**Permissions:**
| id | resource | action |
|---|---|---|
| `perm_conv_read_own` | conversations | read_own |
| `perm_conv_create` | conversations | create |
| `perm_doc_read` | documents | read |
| `perm_doc_upload` | documents | upload |
| `perm_admin_access` | admin_panel | access |
| `perm_audit_view` | audit | view |

**Role → Permission mapping:**
- `superadmin` → all permissions
- `member` → `perm_conv_read_own`, `perm_conv_create`, `perm_doc_read`, `perm_doc_upload`

**Default departments:**
`HR`, `Management`, `Marketing`, `Technical` (all status=active)

---

## 2. Password Hashing

**Algorithm:** PBKDF2-HMAC-SHA256, 260 000 iterations (OWASP 2024 recommendation), 32-byte random salt per user.

**Format stored in `password_hash`:** `pbkdf2_sha256$<base64-salt>$<base64-hash>`

**Implementation:** `backend/services/auth.py` using Python stdlib `hashlib` + `secrets`.
No new package required for password hashing.

```
hash_password(password: str) -> str
verify_password(password: str, stored_hash: str) -> bool  # timing-safe via secrets.compare_digest
```

---

## 3. Authentication Flow

### 3.1 First-run bootstrap

**CLI script:** `python scripts/setup.py`

Behaviour:
1. Calls `init_db()` + seeds roles/permissions/departments
2. Checks `SELECT COUNT(*) FROM users` — if > 0, prints "Setup already complete" and exits
3. Prompts: `Admin username:`, `Password:` (getpass), `Confirm password:`
4. Validates: username non-empty, password ≥ 8 chars, match
5. Creates user row with `role_id='superadmin'`, `is_active=1`
6. Prints `✓ Admin created. Start the app and log in at http://localhost:3000/login`

**App startup detection:**
`GET /api/auth/status` — public endpoint, returns:
- `{"setup_required": true}` if `users` table is empty
- `{"authenticated": false}` if no valid session cookie
- `{"authenticated": true, "user": {...}}` if session valid

Frontend middleware reads this on every page load and redirects accordingly.

---

### 3.2 Login

`POST /api/auth/login` — public (no auth required)

Request body: `{"username": "...", "password": "..."}`

Steps:
1. **Rate limit check** — uses existing `rate_limit_counters` table, key `login_ip_{ip}`, window = 15 min, limit = 5 attempts. Raises 429 if exceeded.
2. **User lookup** — `SELECT * FROM users WHERE username = ?`
3. **Timing-safe verify** — always runs `verify_password()` even if user not found (dummy hash, prevents timing oracle)
4. **Active check** — `is_active = 1`
5. **MFA check** — if `mfa_enabled = 1`: return `{"mfa_required": true, "temp_token": "<32-byte hex>"}` (Phase 2; token stored in `rate_limit_counters` with 5-min TTL as a sentinel row). Phase 1: `mfa_enabled` is always 0, this branch never executes.
6. **Session creation** — insert into `user_sessions`: `session_id = secrets.token_hex(32)`, `expires_at = now + 8h`, log `ip_address`, `user_agent`
7. **Lazy cleanup** — delete `user_sessions` rows where `expires_at < now` (same connection, before insert)
8. **Rate limit reset** — delete the `login_ip_{ip}` counter row on success
9. **Set cookie** — `rag_session=<session_id>; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800`
10. **Audit log** — `action=login_success`, `resource_type=auth`, `decision=allow`
11. **Return** — `{id, username, name, role_name, role_id, department_id, permissions: [...]}`

On failure: 401 `"Invalid credentials"` always (never reveals whether username exists). Increment rate-limit counter. Audit `login_failed` / `login_inactive`.

---

### 3.3 Session resolution (`get_current_user` dependency)

Replaces the existing `get_current_user(x_user_id: Header)` dependency in `main.py`.

```
get_current_user(request: Request) -> User
  1. Read cookie rag_session
  2. SELECT * FROM user_sessions WHERE session_id = ?
  3. If not found → 401
  4. If expires_at < now → delete row → 401 "Session expired"
  5. SELECT * FROM users JOIN roles WHERE users.id = session.user_id
  6. If is_active = 0 → DELETE FROM user_sessions WHERE user_id = ? → 401 "Account disabled"
  7. Return User(id, username, name, role_id, role_name, department_id, permissions=[...])
```

`User` dataclass gains: `role_id`, `role_name`, `permissions: list[str]` (list of `"resource:action"` strings).

The `X-User-Id` header path is **removed entirely**. All existing endpoints that use `Depends(get_current_user)` continue to work — only the dependency implementation changes.

---

### 3.4 Logout

`POST /api/auth/logout` — authenticated

1. `DELETE FROM user_sessions WHERE session_id = ?`
2. `response.delete_cookie("rag_session")`
3. Audit `logout`
4. Return `{"ok": true}`

---

### 3.5 Current user

`GET /api/auth/me` — authenticated

Returns the same shape as the login response. Used by the frontend on page load to restore auth state.

---

### 3.6 Password change (self)

`POST /api/auth/change-password`

Body: `{"current_password": "...", "new_password": "..."}`

1. Verify `current_password` against stored hash
2. Validate new password ≥ 8 chars
3. Hash and update
4. `DELETE FROM user_sessions WHERE user_id = ? AND session_id != <current>` (keeps current session alive)
5. Audit `password_changed`

---

## 4. Admin API — `/api/admin/*`

All endpoints require `perm_admin_access` permission. A helper `require_admin` dependency checks `"admin_panel:access" in user.permissions` and raises 403 otherwise.

### 4.1 Users

| Method | Path | Action |
|---|---|---|
| `GET` | `/api/admin/users` | List all users (paginated, filterable by dept/role/active) |
| `POST` | `/api/admin/users` | Create user (username, password, name, role_id, department_id) |
| `GET` | `/api/admin/users/{id}` | Get user detail |
| `PATCH` | `/api/admin/users/{id}` | Edit name / department / role / is_active |
| `POST` | `/api/admin/users/{id}/reset-password` | Set new password → invalidate all sessions |
| `DELETE` | `/api/admin/users/{id}` | Soft-deactivate (is_active=0); never hard-delete |

Password set by admin: validated ≥ 8 chars; user's all existing sessions deleted immediately.

### 4.2 Departments

| Method | Path | Action |
|---|---|---|
| `GET` | `/api/admin/departments` | List all (incl. archived) |
| `POST` | `/api/admin/departments` | Create (name, code) |
| `PATCH` | `/api/admin/departments/{id}` | Rename or change status (active/archived) |

Departments with active users cannot be archived (returns 409 with user count).
The `code` column is new (not in the existing schema); the migration script fills it from the department `id` for existing rows (e.g. `dept-hr` → `'HR'`).

### 4.3 Roles

| Method | Path | Action |
|---|---|---|
| `GET` | `/api/admin/roles` | List all roles + their permissions |
| `POST` | `/api/admin/roles` | Create custom role |
| `PATCH` | `/api/admin/roles/{id}` | Rename / update description |
| `DELETE` | `/api/admin/roles/{id}` | Delete if `is_system=0` and no users assigned |
| `PUT` | `/api/admin/roles/{id}/permissions` | Replace full permission set for role |

### 4.4 Permissions

| Method | Path | Action |
|---|---|---|
| `GET` | `/api/admin/permissions` | List all defined permissions |

Permissions are seeded — admin cannot create/delete them (they reflect capabilities in code). Admin assigns them to roles.

### 4.5 Audit Log

| Method | Path | Action |
|---|---|---|
| `GET` | `/api/admin/audit-log` | Paginated, filterable by user/action/date-range/resource_type |

Response per row: `timestamp, user_id, username, action, resource_type, resource_id, decision, ip_address, details`.
No delete endpoint exists. Immutable by design.

### 4.6 System Stats

| Method | Path | Action |
|---|---|---|
| `GET` | `/api/admin/stats` | Active users, total docs indexed, Qdrant point count, storage bytes, queue depth |

---

## 5. Conversation Privacy Model

**Rule:** every `list_conversations` / `get_conversation` call filters `owner_user_id = current_user.id` only. No dept-admin override in the chat UI.

**Admin visibility:** admin sees conversation *metadata* only via the audit log (`conversation_created`, `conversation_deleted`, etc.) — not message content. This preserves end-to-end confidentiality while satisfying compliance.

**Deleted conversations:** soft-delete sets `status='deleted'`. The row, all messages (encrypted), and all audit entries are retained forever. The user's UI never shows them again.

---

## 6. Frontend Routing

### Pages

| Route | Visibility | Description |
|---|---|---|
| `/login` | Public | Login form |
| `/setup-required` | Public | "Run setup script" screen |
| `/` | Authenticated | Main chat UI (unchanged) |
| `/admin` | Admin only | Settings panel (gear icon) |

### Next.js middleware (`middleware.ts`)

Runs on every request before rendering:

```
1. GET /api/auth/status (cached 30s)
2. setup_required → redirect /setup-required
3. path == /login → allow
4. no session cookie → redirect /login
5. path starts with /admin AND role != superadmin → redirect /
6. allow
```

### Gear icon

Rendered in `ConversationSidebar.tsx` only when `user.role_id === 'superadmin'`. Links to `/admin`. Non-admin users see no gear icon and get a 403 if they navigate to `/admin` directly.

### Login page (`/login`)

- Username + password fields
- "Invalid credentials" error (generic)
- On 429: "Too many attempts. Try again in 15 minutes."
- On success: redirects to `/`
- No "forgot password" link (admin resets passwords)

### Admin panel (`/admin`)

Tabbed layout with gear icon header. Tabs:

1. **Users** — table + Create/Edit/Deactivate/Reset-password actions
2. **Departments** — table + Create/Rename/Archive actions
3. **Roles** — table + Create/Edit/Delete + permission checkboxes
4. **Audit Log** — filterable table, no edit/delete UI
5. **System** — stats cards (active users, docs indexed, storage, queue)

---

## 7. New Backend Services

| File | Responsibility |
|---|---|
| `backend/services/auth.py` | `hash_password`, `verify_password`, `create_session`, `resolve_session`, `login_rate_limit` |
| `backend/services/admin.py` | User/dept/role CRUD, audit log queries, system stats |
| `backend/scripts/setup.py` | First-run bootstrap CLI |
| `backend/database/migrate_auth.py` | One-time schema migration (rename old users table, recreate, copy) |

Existing files modified:
- `backend/database/schema.sql` — new tables added
- `backend/services/iam.py` — `User` dataclass gains `role_id`, `role_name`, `permissions`; `init_seed_data()` seeds roles/permissions/departments
- `backend/api/main.py` — `get_current_user` replaced; new `/api/auth/*` and `/api/admin/*` routers registered
- `backend/services/conversations.py` — `list_conversations` removes dept-admin clause; strict owner-only filter

New frontend files:
- `frontend/src/middleware.ts` — route protection
- `frontend/src/app/login/page.tsx` — login form
- `frontend/src/app/admin/page.tsx` — admin panel (tabs)
- `frontend/src/app/setup-required/page.tsx` — setup screen
- `frontend/src/lib/auth.ts` — `getMe()`, `login()`, `logout()` API helpers

Existing frontend files modified:
- `frontend/src/app/page.tsx` — reads user from auth context; shows gear icon for admins
- `frontend/src/components/ConversationSidebar.tsx` — gear icon; logout button
- `frontend/src/lib/chatAdapter.ts` — removes `X-User-Id` header (cookie is automatic)

---

## 8. New Package

```
# requirements.txt addition
pyotp        # Phase 2: TOTP MFA — imported but not called in Phase 1
```

No other new packages. All other functionality uses Python stdlib (`hashlib`, `secrets`, `http.cookies`) and existing dependencies.

---

## 9. Security Checklist

- [ ] PBKDF2-HMAC-SHA256, 260 000 iterations, per-user 32-byte salt
- [ ] `secrets.compare_digest` for timing-safe comparison
- [ ] Generic "Invalid credentials" on all login failures
- [ ] Dummy hash check when username not found (prevents timing oracle)
- [ ] Rate limit: 5 attempts / 15 min / IP via existing `rate_limit_counters`
- [ ] `HttpOnly; SameSite=Strict` session cookie — not accessible from JS
- [ ] Session deleted immediately on logout
- [ ] All sessions deleted when user deactivated or password reset
- [ ] Lazy session cleanup on every login
- [ ] Admin panel: protected at middleware (frontend) AND `require_admin` dependency (backend)
- [ ] Gear icon hidden from non-admin users in the DOM
- [ ] Audit log: no DELETE path exists anywhere in the codebase
- [ ] `mfa_secret` column present (Phase 2 ready); encrypted with existing AES-GCM master key when set
- [ ] `pyotp` imported but gated behind `mfa_enabled` flag — no TOTP calls in Phase 1

---

## 10. Out of Scope (Phase 2)

- TOTP MFA enrolment + verification endpoints
- Email notifications (air-gapped — no email server)
- SSO / LDAP integration
- Per-document access rules (current model: all authenticated users can read indexed documents)
- Audit log export (CSV/PDF)
- Session listing UI (admin sees active sessions per user)
