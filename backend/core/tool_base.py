"""Tool base class and ToolMetadata — the building blocks for all pluggable components."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ToolMetadata:
    """Tool metadata for discovery and registration."""
    name: str                                    # e.g. "reader:pdf"
    version: str                                 # e.g. "1.0.0"
    tool_type: str                               # "reader" | "parser" | "chunker" | "embedder"
    description: str
    author: str = "Handwerk RAG"

    # Requirements
    dependencies: List[str] = field(default_factory=list)   # ["pdfplumber>=0.9.0"]
    python_min: str = "3.9"

    # Capabilities (format-specific flags — readers use this for format routing)
    capabilities: Dict[str, Any] = field(default_factory=dict)

    # Status
    is_production: bool = True
    is_async: bool = True
    is_experimental: bool = False

    # Performance hints
    estimated_time_per_mb: float = 1.0
    max_parallel_tasks: int = 1


class Tool(ABC):
    """Base class for all pluggable tools (readers, parsers, chunkers, embedders)."""

    metadata: ToolMetadata = None   # subclasses must override

    def __init__(self):
        """Validate metadata exists and all declared dependencies are importable."""
        if not self.metadata:
            raise ValueError(f"{self.__class__.__name__} must define a class-level 'metadata' attribute")
        self._validate_dependencies()

    def _validate_dependencies(self) -> None:
        """Hard-check dependencies at instantiation time.

        Raises ImportError with install instructions if any declared dependency
        cannot be imported. This blocks tool instantiation — callers that want
        soft failure should catch ImportError around register_tool().
        """
        import importlib
        for dep in self.metadata.dependencies:
            # "package>=1.0" → "package"; try pip name, underscore variant, lowercase
            base = dep.split(">=")[0].split("==")[0].split("<")[0].strip()
            candidates = [base, base.replace("-", "_"), base.lower()]
            importable = False
            for name in candidates:
                try:
                    importlib.import_module(name)
                    importable = True
                    break
                except ImportError:
                    pass
            if not importable:
                raise ImportError(
                    f"Tool '{self.metadata.name}' requires '{dep}'. "
                    f"Install with: pip install {base}"
                )

    @abstractmethod
    async def execute(self, input_data: Any, **kwargs) -> Any:
        """Execute tool logic. Input/output types are defined by each tool type."""

    async def validate_input(self, input_data: Any) -> tuple[bool, Optional[str]]:
        """Override to add input validation. Returns (is_valid, error_message)."""
        return True, None

    def get_metadata(self) -> ToolMetadata:
        """Return this tool's ToolMetadata (name, version, capabilities, …)."""
        return self.metadata

    def __repr__(self) -> str:
        """Return a brief 'name vX.Y.Z' string for logging and debugging."""
        return f"{self.metadata.name} v{self.metadata.version}"
