"""Small utilities used by command-line modules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


def ensure_parent(path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def to_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    return value


def write_json(payload: dict[str, Any], path: str | Path) -> Path:
    destination = ensure_parent(path)
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(to_json_value(payload), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return destination
