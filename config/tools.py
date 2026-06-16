"""Load tool configuration from config/tools.yaml."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "tools.yaml"


def load_tool_config(config_path: str = None) -> Dict[str, Any]:
    """Load and return the tools configuration dict.

    Args:
        config_path: Override path to a YAML file. Defaults to config/tools.yaml
                     (same directory as this module).

    Returns:
        Dict with structure: {"tools": {tool_name: {"enabled": bool, "config": {...}}}}

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the YAML is malformed or missing the "tools" key.
    """
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required to load tool config. Install with: pip install pyyaml"
        )

    path = Path(config_path) if config_path else _CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Tool config not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Tool config must be a YAML mapping, got: {type(data).__name__}")

    if "tools" not in data:
        raise ValueError(f"Tool config missing required 'tools' key: {path}")

    logger.info(f"Loaded tool config from {path} ({len(data['tools'])} entries)")
    return data
