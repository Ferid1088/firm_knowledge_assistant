"""Unit tests for auth service: hashing, session creation, rate limiting."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from backend.services.auth import hash_password, verify_password


def test_hash_password_produces_pbkdf2_format():
    h = hash_password("secret123")
    parts = h.split("$")
    assert parts[0] == "pbkdf2_sha256"
    assert len(parts) == 3  # algo$salt$hash


def test_verify_password_correct():
    h = hash_password("secret123")
    assert verify_password("secret123", h) is True


def test_verify_password_wrong():
    h = hash_password("secret123")
    assert verify_password("wrong", h) is False


def test_hash_is_not_deterministic():
    h1 = hash_password("secret123")
    h2 = hash_password("secret123")
    assert h1 != h2


def test_verify_empty_hash_returns_false():
    assert verify_password("anything", "") is False
