"""Configuration loading and portable path resolution."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when the project configuration is invalid."""


def load_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise ConfigError(f"Configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    required_sections = {"project", "paths", "data", "model"}
    missing = sorted(required_sections - set(config))
    if missing:
        raise ConfigError(f"Missing configuration sections: {', '.join(missing)}")

    resolved = deepcopy(config)
    project_root = path.parent.parent
    resolved["_config_path"] = path
    resolved["_project_root"] = project_root

    for key, value in resolved["paths"].items():
        candidate = Path(value).expanduser()
        resolved["paths"][key] = candidate if candidate.is_absolute() else project_root / candidate

    return resolved
