"""Load runtime configuration files from the project-level config/ directory.

config/ contains data files (YAML) only — no Python.
This module is the single place that reads them and returns plain dicts.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# config/ lives at the project root, two levels above this file:
#   backend/core/config_loader.py  →  ../../config/
_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def load_tools_config(config_path: str | None = None) -> Dict[str, Any]:
    """Return the parsed contents of config/tools.yaml.

    Args:
        config_path: Override path. Defaults to <project_root>/config/tools.yaml.

    Returns:
        {"tools": {tool_name: {"enabled": bool, "config": {...}}}}

    Raises:
        FileNotFoundError: config file absent.
        ValueError: YAML malformed or missing "tools" key.
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required — add pyyaml to requirements.txt")

    path = Path(config_path) if config_path else _CONFIG_DIR / "tools.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Tools config not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"tools.yaml must be a YAML mapping, got {type(data).__name__}")
    if "tools" not in data:
        raise ValueError(f"tools.yaml missing required 'tools' key: {path}")

    logger.info(f"Loaded tools config: {path} ({len(data['tools'])} entries)")
    return data
