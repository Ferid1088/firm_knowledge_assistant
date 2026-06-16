"""Shared fixtures for the multi-user persistence tests.

Each test gets an isolated SQLite DB + key files under a temp directory, so
tests never touch the real database/app.db or key material.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    master_key_path = tmp_path / "keys" / "master.key"
    signing_key_path = tmp_path / "keys" / "signing_ed25519.pem"

    monkeypatch.setattr("backend.database.DATABASE_PATH", str(db_path))
    monkeypatch.setattr("backend.services.security.MASTER_KEY_PATH", str(master_key_path))
    monkeypatch.setattr("backend.services.security.SIGNING_KEY_PATH", str(signing_key_path))

    from backend.database import init_db
    from backend.services import iam

    init_db()
    iam.init_seed_data()
    return db_path
