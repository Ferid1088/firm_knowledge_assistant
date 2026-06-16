"""Tool logging configuration — centralised log-level control for all tool modules."""
from __future__ import annotations

import logging
from typing import Optional

# Modules whose loggers are controlled by configure_tool_logging()
_TOOL_LOGGER_PREFIXES = [
    "backend.core.tool_base",
    "backend.core.tool_registry",
    "backend.core.tool_pipeline",
    "backend.core.tool_loaders",
    "backend.core.tool_health",
    "backend.tools",
]


def configure_tool_logging(
    log_level: str = "INFO",
    handler: Optional[logging.Handler] = None,
    fmt: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
) -> None:
    """Configure log level and optional handler for all tool-related loggers.

    Args:
        log_level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL"
        handler: Optional custom handler. If None, a StreamHandler is added only
                 when the root logger has no handlers configured (avoids duplicate
                 output in applications that configure the root logger themselves).
        fmt: Log format string used when a StreamHandler is created here.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    for prefix in _TOOL_LOGGER_PREFIXES:
        lg = logging.getLogger(prefix)
        lg.setLevel(level)

    if handler is not None:
        handler.setLevel(level)
        for prefix in _TOOL_LOGGER_PREFIXES:
            logging.getLogger(prefix).addHandler(handler)
    elif not logging.root.handlers:
        _h = logging.StreamHandler()
        _h.setLevel(level)
        _h.setFormatter(logging.Formatter(fmt))
        for prefix in _TOOL_LOGGER_PREFIXES:
            logging.getLogger(prefix).addHandler(_h)
