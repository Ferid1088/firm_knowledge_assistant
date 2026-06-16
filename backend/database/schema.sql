-- Auth & IAM schema (Phase 1). Idempotent CREATE TABLE IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS departments (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    code       TEXT NOT NULL UNIQUE,
    status     TEXT NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roles (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT,
    is_system   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS permissions (
    id          TEXT PRIMARY KEY,
    resource    TEXT NOT NULL,
    action      TEXT NOT NULL,
    description TEXT,
    UNIQUE (resource, action)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id TEXT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL DEFAULT '',
    name          TEXT NOT NULL,
    department_id TEXT NOT NULL REFERENCES departments(id),
    role_id       TEXT NOT NULL REFERENCES roles(id),
    is_active     INTEGER NOT NULL DEFAULT 1,
    mfa_enabled          INTEGER NOT NULL DEFAULT 0,
    mfa_secret           TEXT,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id             TEXT PRIMARY KEY,
    tenant_id      TEXT NOT NULL,
    department_id  TEXT NOT NULL REFERENCES departments(id),
    owner_user_id  TEXT NOT NULL REFERENCES users(id),
    title          TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('draft', 'active', 'archived', 'deleted')),
    wrapped_dek    BLOB NOT NULL,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_shares (
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    user_id         TEXT NOT NULL REFERENCES users(id),
    permission      TEXT NOT NULL CHECK (permission IN ('view', 'comment', 'edit')),
    granted_by      TEXT NOT NULL REFERENCES users(id),
    granted_at      TEXT NOT NULL,
    PRIMARY KEY (conversation_id, user_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id                   TEXT PRIMARY KEY,
    conversation_id      TEXT NOT NULL REFERENCES conversations(id),
    role                 TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    ciphertext           BLOB NOT NULL,
    nonce                BLOB NOT NULL,
    content_hash         TEXT NOT NULL,
    signature            BLOB NOT NULL,
    lang                 TEXT NOT NULL,
    claims_json          TEXT,
    artifact_chunks_json TEXT,
    created_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS user_sessions (
    session_id   TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    ip_address   TEXT NOT NULL,
    user_agent   TEXT NOT NULL,
    mfa_verified INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id
    ON user_sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at
    ON user_sessions(expires_at);

CREATE TABLE IF NOT EXISTS rate_limit_counters (
    key          TEXT NOT NULL,
    window_type  TEXT NOT NULL,
    window_start TEXT NOT NULL,
    count        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (key, window_type, window_start)
);

-- Document types (admin-managed; used as chunk metadata and access control)
CREATE TABLE IF NOT EXISTS document_types (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    code        TEXT NOT NULL UNIQUE,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'archived')),
    created_at  TEXT NOT NULL
);

-- Per-user document type access (if NO rows exist for a user, they see ALL active types)
CREATE TABLE IF NOT EXISTS user_doc_type_permissions (
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    doc_type_id TEXT NOT NULL REFERENCES document_types(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, doc_type_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL,
    conversation_id TEXT REFERENCES conversations(id),
    action          TEXT NOT NULL,
    details_json    TEXT,
    resource_type   TEXT,
    decision        TEXT,
    ip_address      TEXT,
    created_at      TEXT NOT NULL
);
