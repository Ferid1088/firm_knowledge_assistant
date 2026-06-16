"""Tool loaders — load enabled tools from config and list available tools by type."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def load_enabled_tools(registry: Any, config: Dict[str, Any]) -> List[str]:
    """Load tools that are marked enabled in the config dict.

    Args:
        registry: A ToolRegistry instance.
        config: Dict loaded from config/tools.yaml (see config/tools.py).

    Returns:
        List of tool names that were successfully enabled.
    """
    enabled: List[str] = []
    tools_cfg: Dict[str, Any] = config.get("tools", {})

    for tool_name, tool_cfg in tools_cfg.items():
        if not tool_cfg.get("enabled", True):
            logger.info(f"Tool '{tool_name}' is disabled in config — skipping")
            continue
        if registry.has_tool(tool_name):
            enabled.append(tool_name)
            logger.debug(f"Tool '{tool_name}' confirmed enabled")
        else:
            logger.warning(
                f"Tool '{tool_name}' listed in config but not registered "
                f"(missing dependency or not discovered)"
            )

    return enabled


def list_available_tools(registry: Any, tool_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all registered tools, optionally filtered by type.

    Args:
        registry: A ToolRegistry instance.
        tool_type: Optional filter — "reader", "parser", "chunker", "embedder".

    Returns:
        List of tool metadata dicts (name, version, type, description, is_production,
        capabilities, dependencies).
    """
    return registry.list_tools(tool_type=tool_type, include_experimental=False)
