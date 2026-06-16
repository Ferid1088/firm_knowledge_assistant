from backend.services import iam
from backend.services.conversations import ConversationError, get_conversation
from backend.services.sharing import share_conversation


def test_owner_can_access_own_conversation(db):
    alice = iam.get_user("user-bob")
    from backend.services.conversations import create_conversation

    conv = create_conversation(alice, "Bob's notes")
    fetched = get_conversation(conv["id"], alice)
    assert fetched["id"] == conv["id"]


def test_other_user_cannot_access_private_conversation(db):
    from backend.services.conversations import create_conversation

    bob = iam.get_user("user-bob")
    carol = iam.get_user("user-carol")  # different department, not shared

    conv = create_conversation(bob, "Bob's private conversation")

    try:
        get_conversation(conv["id"], carol)
        assert False, "expected ConversationError"
    except ConversationError as e:
        assert "forbidden" in str(e)


def test_access_succeeds_after_share(db):
    from backend.services.conversations import create_conversation

    bob = iam.get_user("user-bob")
    carol = iam.get_user("user-carol")

    conv = create_conversation(bob, "Shared with Carol")
    share_conversation(conv["id"], bob, carol.id, "view")

    fetched = get_conversation(conv["id"], carol)
    assert fetched["id"] == conv["id"]
