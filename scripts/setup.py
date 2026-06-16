#!/usr/bin/env python3
"""First-run bootstrap: initialise the database and create the first admin user.

Usage:
    python scripts/setup.py
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.database import init_db
from backend.services.iam import init_seed_data, count_users, create_user
from backend.services.auth import hash_password


def main() -> None:
    init_db()
    init_seed_data()

    if count_users() > 0:
        print("Setup already complete — users exist. Use /api/admin/users to manage them.")
        sys.exit(0)

    print("=== Local RAG — First-run setup ===\n")

    username = input("Admin username: ").strip()
    if not username:
        print("Error: username cannot be empty.")
        sys.exit(1)

    while True:
        password = getpass.getpass("Password (≥ 8 chars): ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match. Try again.")
            continue
        if len(password) < 8:
            print("Password must be at least 8 characters.")
            continue
        break

    pw_hash = hash_password(password)
    user = create_user(
        username=username,
        password_hash=pw_hash,
        name=username.title(),
        department_id="dept-tech",
        role_id="superadmin",
    )
    print(f"\nAdmin '{user.username}' created.")
    print("Start the app and log in at http://localhost:3000/login")


if __name__ == "__main__":
    main()
