"""Local cryptography: key management, message encryption, integrity signing.

Substitutes for the spec's Vault-managed keys and RSA/PKI signing — both kept
fully local/air-gapped per CLAUDE.md (no external KMS, no network calls).

- Master key (AES-256, 32 bytes) wraps each conversation's per-conversation
  data-encryption key (DEK) with AES-256-GCM. Analogous to "Vault-managed
  encryption keys" but the "vault" is a local keyfile with restricted
  permissions.
- Ed25519 keypair signs the content_hash of every message for integrity
  verification — substitutes the spec's RSA-signed message integrity.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

from backend.config import MASTER_KEY_PATH, SIGNING_KEY_PATH

_NONCE_SIZE = 12  # AES-GCM standard nonce size


def _load_or_create_bytes(path: str, generator) -> bytes:
    p = Path(path)
    if p.exists():
        return p.read_bytes()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = generator()
    p.write_bytes(data)
    os.chmod(p, 0o600)
    return data


def _master_key() -> bytes:
    return _load_or_create_bytes(MASTER_KEY_PATH, lambda: AESGCM.generate_key(bit_length=256))


def _signing_key() -> Ed25519PrivateKey:
    raw = _load_or_create_bytes(
        SIGNING_KEY_PATH,
        lambda: Ed25519PrivateKey.generate().private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    )
    return Ed25519PrivateKey.from_private_bytes(raw)


# ── Data-encryption keys (per conversation) ──────────────────────────────────

def generate_dek() -> bytes:
    """A fresh 256-bit key for one conversation's message content."""
    return AESGCM.generate_key(bit_length=256)


def wrap_dek(dek: bytes) -> bytes:
    """Encrypt a conversation DEK with the local master key (Vault substitute)."""
    aesgcm = AESGCM(_master_key())
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = aesgcm.encrypt(nonce, dek, None)
    return nonce + ciphertext


def unwrap_dek(wrapped: bytes) -> bytes:
    aesgcm = AESGCM(_master_key())
    nonce, ciphertext = wrapped[:_NONCE_SIZE], wrapped[_NONCE_SIZE:]
    return aesgcm.decrypt(nonce, ciphertext, None)


# ── Message content encryption ────────────────────────────────────────────────

def encrypt_message(plaintext: str, dek: bytes) -> tuple[bytes, bytes]:
    """AES-256-GCM encrypt -> (ciphertext, nonce)."""
    aesgcm = AESGCM(dek)
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt_message(ciphertext: bytes, nonce: bytes, dek: bytes) -> str:
    aesgcm = AESGCM(dek)
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


# ── Integrity: content hash + signature ───────────────────────────────────────

def content_hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def sign(digest_hex: str) -> bytes:
    return _signing_key().sign(digest_hex.encode("utf-8"))


def verify(digest_hex: str, signature: bytes) -> bool:
    public_key: Ed25519PublicKey = _signing_key().public_key()
    try:
        public_key.verify(signature, digest_hex.encode("utf-8"))
        return True
    except Exception:
        return False
