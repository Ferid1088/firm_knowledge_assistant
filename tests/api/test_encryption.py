import sqlite3

from backend.services import iam
from backend.services.conversations import create_conversation, add_message, get_messages


def test_message_stored_encrypted_and_decrypts_correctly(db):
    alice = iam.get_user("user-alice")
    conv = create_conversation(alice, "Encryption test")

    plaintext = "Wie hoch ist die maximale Belastung laut Tabelle 4.2?"
    add_message(conv["id"], "user", plaintext, "de")

    # Raw row in SQLite must not contain the plaintext.
    raw = sqlite3.connect(db)
    raw.row_factory = sqlite3.Row
    row = raw.execute(
        "SELECT ciphertext, nonce FROM messages WHERE conversation_id = ?", (conv["id"],)
    ).fetchone()
    raw.close()

    assert row is not None
    assert plaintext.encode("utf-8") not in bytes(row["ciphertext"])

    # decrypt_message round-trips via get_messages.
    messages = get_messages(conv["id"])
    assert len(messages) == 1
    assert messages[0]["text"] == plaintext
