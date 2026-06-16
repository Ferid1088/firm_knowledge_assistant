from backend.database import get_connection
from backend.services import iam, security
from backend.services.audit import verify_message_integrity
from backend.services.conversations import create_conversation, add_message


def _get_message_row(conversation_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ?", (conversation_id,)
    ).fetchone()
    conn.close()
    return dict(row)


def test_untampered_message_verifies(db):
    alice = iam.get_user("user-alice")
    conv = create_conversation(alice, "Integrity test")
    text = "Der Grenzwert betraegt 230 V."
    add_message(conv["id"], "user", text, "de")

    row = _get_message_row(conv["id"])
    assert verify_message_integrity(row, text) is True


def test_tampered_content_hash_fails_verification(db):
    alice = iam.get_user("user-alice")
    conv = create_conversation(alice, "Integrity test 2")
    text = "Der Grenzwert betraegt 230 V."
    add_message(conv["id"], "user", text, "de")

    row = _get_message_row(conv["id"])
    row["content_hash"] = security.content_hash("tampered text")

    assert verify_message_integrity(row, text) is False


def test_tampered_signature_fails_verification(db):
    alice = iam.get_user("user-alice")
    conv = create_conversation(alice, "Integrity test 3")
    text = "Der Grenzwert betraegt 230 V."
    add_message(conv["id"], "user", text, "de")

    row = _get_message_row(conv["id"])
    tampered = bytearray(row["signature"])
    tampered[0] ^= 0xFF
    row["signature"] = bytes(tampered)

    assert verify_message_integrity(row, text) is False
