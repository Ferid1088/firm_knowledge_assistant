"""ToolPipeline and PipelineBuilder — sequential tool execution."""
from __future__ import annotations

import logging
from typing import Any, List

from backend.core.tool_registry import get_registry

logger = logging.getLogger(__name__)


class ToolPipeline:
    """Execute a fixed sequence of tools, passing output of each as input to the next."""

    def __init__(self, tool_names: List[str]):
        self.tool_names = tool_names
        registry = get_registry()
        self.tools = []
        for name in tool_names:
            tool = registry.get_tool(name)
            if not tool:
                raise ValueError(f"Tool not found in registry: {name}")
            self.tools.append(tool)

    async def execute(self, input_data: Any, **kwargs) -> Any:
        current = input_data
        for i, tool in enumerate(self.tools):
            name = self.tool_names[i]
            logger.info(f"[{i + 1}/{len(self.tools)}] Executing: {name}")

            is_valid, error = await tool.validate_input(current)
            if not is_valid:
                raise ValueError(f"Tool {name} validation failed: {error}")

            current = await tool.execute(current, **kwargs)

        return current


class PipelineBuilder:
    """Fluent builder for ToolPipeline."""

    def __init__(self):
        self._tools: List[str] = []

    def add(self, tool_name: str) -> "PipelineBuilder":
        self._tools.append(tool_name)
        return self

    def build(self) -> ToolPipeline:
        return ToolPipeline(self._tools)
