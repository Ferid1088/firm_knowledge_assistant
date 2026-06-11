from __future__ import annotations

import logging
import os
from typing import Any, Callable

from config import LANGFUSE_ENABLED, LANGFUSE_HOST

logger = logging.getLogger(__name__)

_REQUIRED_LANGFUSE_ENV = (
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
)
_logged_messages: set[str] = set()


def _log_once(level: int, message: str) -> None:
    if message in _logged_messages:
        return
    _logged_messages.add(message)
    logger.log(level, message)


def _noop_decorator(*decorator_args, **decorator_kwargs):
    if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
        return decorator_args[0]

    def decorator(func: Callable):
        return func

    return decorator


def langfuse_status() -> dict[str, Any]:
    missing = [name for name in _REQUIRED_LANGFUSE_ENV if not os.environ.get(name)]
    active = LANGFUSE_ENABLED and not missing

    if not LANGFUSE_ENABLED:
        message = (
            "Langfuse tracing disabled: LANGFUSE_ENABLED is false or unset. "
            "Export LANGFUSE_ENABLED=true plus LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY "
            "before starting the backend."
        )
    elif missing:
        message = (
            "Langfuse tracing misconfigured: missing required env vars "
            f"{', '.join(missing)}. Traces will not be sent."
        )
    else:
        message = f"Langfuse tracing enabled for host={LANGFUSE_HOST}."

    return {
        "enabled_flag": LANGFUSE_ENABLED,
        "host": LANGFUSE_HOST,
        "missing_env": missing,
        "active": active,
        "message": message,
    }


def describe_langfuse_status() -> str:
    return str(langfuse_status()["message"])


def build_langfuse_callbacks() -> list:
    status = langfuse_status()
    if not status["active"]:
        _log_once(logging.WARNING, status["message"])
        return []

    try:
        from langfuse.callback import CallbackHandler
    except Exception as exc:
        _log_once(logging.WARNING, f"Failed to import Langfuse CallbackHandler: {exc}")
        return []

    try:
        handler = CallbackHandler(
            host=LANGFUSE_HOST,
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        )
    except Exception as exc:
        _log_once(logging.WARNING, f"Failed to initialize Langfuse callback handler: {exc}")
        return []

    _log_once(logging.INFO, status["message"])
    return [handler]


def observe_if_enabled(*decorator_args, **decorator_kwargs):
    status = langfuse_status()
    if not status["active"]:
        return _noop_decorator(*decorator_args, **decorator_kwargs)

    try:
        from langfuse.decorators import observe
    except Exception as exc:
        _log_once(logging.WARNING, f"Failed to import Langfuse observe decorator: {exc}")
        return _noop_decorator(*decorator_args, **decorator_kwargs)

    return observe(*decorator_args, **decorator_kwargs)