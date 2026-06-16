import pytest

from backend.config import RATE_LIMIT_MSGS_PER_HOUR, RATE_LIMIT_CONVERSATIONS_PER_DAY
from backend.services.rate_limit import apply_agent_rate_limits, RateLimitError, get_usage


def test_message_rate_limit_enforced(db):
    user_id = "user-alice"

    for _ in range(RATE_LIMIT_MSGS_PER_HOUR):
        apply_agent_rate_limits(user_id, "message")

    assert get_usage(user_id, "message")["used"] == RATE_LIMIT_MSGS_PER_HOUR

    with pytest.raises(RateLimitError):
        apply_agent_rate_limits(user_id, "message")


def test_conversation_rate_limit_enforced(db):
    user_id = "user-bob"

    for _ in range(RATE_LIMIT_CONVERSATIONS_PER_DAY):
        apply_agent_rate_limits(user_id, "conversation")

    with pytest.raises(RateLimitError):
        apply_agent_rate_limits(user_id, "conversation")


def test_rate_limits_are_per_user(db):
    for _ in range(RATE_LIMIT_MSGS_PER_HOUR):
        apply_agent_rate_limits("user-carol", "message")

    # A different user is unaffected by user-carol's usage.
    apply_agent_rate_limits("user-dave", "message")
    assert get_usage("user-dave", "message")["used"] == 1
