"""Tool health checks — verify each registered tool can execute a minimal probe."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def check_tool_health(registry: Any) -> List[Dict[str, Any]]:
    """Run a lightweight health probe on every registered tool.

    For each tool this records:
    - name, version, type
    - status: "ok" | "error"
    - latency_ms: time to call get_metadata() (dependency validation already
      passed at registration; a proper execute() probe requires a real input
      file which we don't have here)
    - error: error message if status == "error"

    Returns:
        List of per-tool health dicts.
    """
    results: List[Dict[str, Any]] = []

    for name, tool in registry.tools.items():
        start = time.monotonic()
        status = "ok"
        error_msg = ""
        try:
            meta = tool.get_metadata()
            _ = repr(tool)          # exercises __repr__
            _ = meta.dependencies   # ensures metadata is accessible
        except Exception as exc:
            status = "error"
            error_msg = str(exc)
        finally:
            latency_ms = round((time.monotonic() - start) * 1000, 2)

        meta = registry.metadata.get(name)
        results.append({
            "name": name,
            "version": meta.version if meta else "unknown",
            "type": meta.tool_type if meta else "unknown",
            "status": status,
            "latency_ms": latency_ms,
            "error": error_msg,
        })
        if status == "ok":
            logger.debug(f"[health] {name}: ok ({latency_ms} ms)")
        else:
            logger.error(f"[health] {name}: ERROR — {error_msg}")

    return results
