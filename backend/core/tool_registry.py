"""ToolRegistry — discovery, registration, and lookup of all pluggable tools."""
from __future__ import annotations

import fnmatch
import importlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Type

from backend.core.tool_base import Tool, ToolMetadata

logger = logging.getLogger(__name__)

# Default search paths used when none are provided to get_registry().
# These must match the actual package layout under backend/.
_DEFAULT_SEARCH_PATHS = [
    "backend/tools/readers",
    "backend/tools/parsers",
    "backend/tools/chunkers",
    "backend/tools/embedders",
]


class ToolRegistry:
    """Manage tool discovery, registration, and execution."""

    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self.metadata: Dict[str, ToolMetadata] = {}
        self.tool_paths: List[Path] = []

    def add_search_path(self, path: str) -> None:
        p = Path(path)
        if p.exists():
            self.tool_paths.append(p)
            logger.info(f"Added tool search path: {path}")

    def register_tool(self, tool_class: Type[Tool], force: bool = False) -> bool:
        """Instantiate and register a tool class.

        ImportError (missing dependency) is caught and logged — it does NOT
        propagate so that discovery can continue past unavailable tools.
        """
        try:
            instance = tool_class()
            meta = instance.get_metadata()
            name = meta.name

            if name in self.tools and not force:
                logger.warning(f"Tool {name} already registered; skipping (use force=True to overwrite)")
                return False

            self.tools[name] = instance
            self.metadata[name] = meta
            logger.info(f"Registered tool: {name} v{meta.version} ({meta.tool_type})")
            return True

        except ImportError as e:
            logger.warning(f"Skipping {tool_class.__name__}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to register {tool_class.__name__}: {e}")
            return False

    def discover_tools(
        self,
        search_paths: List[str] = None,
        base_module: str = None,
    ) -> None:
        """Discover and register Tool subclasses found under search_paths.

        Args:
            search_paths: Filesystem paths to scan (e.g. ["backend/tools/readers"]).
            base_module: Dotted Python package that corresponds to the project root,
                used to build correct module names (e.g. passing "backend" means a
                file at "backend/tools/readers/csv.py" becomes "backend.tools.readers.csv").
                When None, module names are computed relative to search_dir.parent —
                only correct when the search dir IS a top-level package.
        """
        paths = search_paths or [str(p) for p in self.tool_paths] or ["tools/"]

        for search_path in paths:
            search_dir = Path(search_path)
            if not search_dir.exists():
                logger.warning(f"Search path does not exist: {search_path}")
                continue

            logger.info(f"Discovering tools in: {search_path}")

            for py_file in search_dir.rglob("*.py"):
                if py_file.name.startswith("_"):
                    continue

                if base_module:
                    # Build module name from the known package root.
                    # e.g. base_module="backend", py_file="backend/tools/readers/csv.py"
                    # → "backend.tools.readers.csv"
                    base_path = Path(base_module.replace(".", "/"))
                    try:
                        rel = py_file.relative_to(base_path.parent)
                        module_name = str(rel)[:-3].replace("/", ".").replace("\\", ".")
                    except ValueError:
                        # py_file is not under base_path — fall back to old behaviour
                        rel_path = py_file.relative_to(search_dir.parent)
                        module_name = str(rel_path)[:-3].replace("/", ".").replace("\\", ".")
                else:
                    rel_path = py_file.relative_to(search_dir.parent)
                    module_name = str(rel_path)[:-3].replace("/", ".").replace("\\", ".")

                try:
                    module = importlib.import_module(module_name)
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type)
                                and issubclass(attr, Tool)
                                and attr is not Tool
                                and hasattr(attr, "metadata")
                                and attr.metadata is not None    # skip abstract bases
                                # Only register classes defined in THIS module, not
                                # base classes imported from elsewhere (e.g. FileReaderTool).
                                and getattr(attr, "__module__", None) == module_name):
                            self.register_tool(attr, force=False)
                except Exception as e:
                    logger.debug(f"Could not import {module_name}: {e}")

    def get_tool(self, tool_name: str) -> Optional[Tool]:
        tool = self.tools.get(tool_name)
        if not tool:
            logger.warning(f"Tool not found: {tool_name}")
        return tool

    def list_tools(
        self,
        tool_type: str = None,
        pattern: str = None,
        include_experimental: bool = False,
    ) -> List[Dict]:
        result = []
        for name, meta in self.metadata.items():
            if meta.is_experimental and not include_experimental:
                continue
            if tool_type and meta.tool_type != tool_type:
                continue
            if pattern and not fnmatch.fnmatch(name, pattern):
                continue
            result.append({
                "name": name,
                "version": meta.version,
                "type": meta.tool_type,
                "description": meta.description,
                "is_production": meta.is_production,
                "capabilities": meta.capabilities,
                "dependencies": meta.dependencies,
            })
        return result

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self.tools

    def export_metadata(self, output_file: str = "tools_manifest.json") -> None:
        manifest = {
            "generated_at": datetime.now().isoformat(),
            "tools": [
                {
                    "name": meta.name,
                    "version": meta.version,
                    "type": meta.tool_type,
                    "description": meta.description,
                    "is_production": meta.is_production,
                    "dependencies": meta.dependencies,
                    "capabilities": meta.capabilities,
                }
                for meta in self.metadata.values()
            ],
        }
        with open(output_file, "w") as f:
            json.dump(manifest, f, indent=2)
        logger.info(f"Tool manifest exported to: {output_file}")

    def __repr__(self) -> str:
        return f"ToolRegistry({len(self.tools)} tools)"


_registry: Optional[ToolRegistry] = None


def get_registry(
    search_paths: List[str] = None,
    auto_discover: bool = True,
) -> ToolRegistry:
    """Return (or lazily initialize) the global tool registry.

    On first call, adds the four default search paths, runs auto-discovery,
    and applies enabled/disabled flags from config/tools.yaml.
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        effective_paths = search_paths if search_paths is not None else _DEFAULT_SEARCH_PATHS
        for path in effective_paths:
            _registry.add_search_path(path)
        if auto_discover and _registry.tool_paths:
            _registry.discover_tools(base_module="backend")

        # Apply enabled/disabled flags from config/tools.yaml.
        try:
            from backend.core.config_loader import load_tools_config
            from backend.core.tool_loaders import load_enabled_tools
            cfg = load_tools_config()
            load_enabled_tools(_registry, cfg)
        except FileNotFoundError:
            logger.warning("config/tools.yaml not found — all discovered tools treated as enabled")
        except Exception as exc:
            logger.warning(f"Could not apply tools config: {exc}")

    return _registry


def reset_registry() -> None:
    """Reset singleton — useful for tests."""
    global _registry
    _registry = None
