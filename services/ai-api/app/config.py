"""Service configuration for the PisGo AI adapter.

Only PisGo's own adapter settings live here. Model-specific constants
(model version, labels, preprocessing) are read from the loaded artifact,
never duplicated.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# --- PisGo design mapping: 4-class classifier -> UI maturity scale 1-7 -------
#
# This is a PISGO DESIGN DECISION, not an agronomic calibration. The CV
# classifier emits one of four maturity classes; the PisGo UI works on a 1-7
# maturity scale. The values below are the anchor points the PisGo team chose
# to map each class onto that scale. `current_maturity` in API responses is a
# probability-weighted blend of these anchors -- an adapter of visual class
# probabilities, not a measured maturity index.
#
# Override without code changes via MATURITY_CLASS_SCALE_JSON, e.g.:
#   MATURITY_CLASS_SCALE_JSON={"unripe": 2.0, "half_ripe": 3.5, "ripe": 5.5, "overripe": 6.5}
MATURITY_CLASS_SCALE: dict[str, float] = {
    "unripe": 2.0,
    "half_ripe": 3.5,
    "ripe": 5.5,
    "overripe": 6.5,
}

# Linear heuristic for days_to_target: assumed maturity gain per day on the
# 1-7 UI scale. Placeholder pending real data; documented as such.
MATURITY_RATE_PER_DAY: float = 0.15

# Banana detection is a HEURISTIC PROXY, not a trained detector. The classifier
# assumes its input is a Cavendish banana photo; the only signal we expose is
# the artifact's `foreground_proxy_ratio` feature (share of pixels that fall in
# a banana-like hue/saturation band). If it is below this threshold we report
# banana_detected=false. Not a precision/recall-validated detector.
BANANA_FOREGROUND_MIN_RATIO: float = 0.02

ADAPTER_VERSION: str = "pisgo-ai-api-v1"

CULTIVAR: str = "cavendish"

MAX_IMAGE_BYTES: int = 10 * 1024 * 1024


def _default_model_path() -> Path:
    return REPO_ROOT / "ml" / "models" / "cavendish_maturity_classifier.joblib"


def _load_class_scale() -> dict[str, float]:
    raw = os.environ.get("MATURITY_CLASS_SCALE_JSON")
    if not raw:
        return dict(MATURITY_CLASS_SCALE)
    parsed = json.loads(raw)
    return {str(k): float(v) for k, v in parsed.items()}


@dataclass(frozen=True)
class Settings:
    model_path: Path = field(default_factory=_default_model_path)
    maturity_class_scale: dict[str, float] = field(default_factory=_load_class_scale)
    maturity_rate_per_day: float = MATURITY_RATE_PER_DAY
    banana_foreground_min_ratio: float = BANANA_FOREGROUND_MIN_RATIO
    adapter_version: str = ADAPTER_VERSION
    cultivar: str = CULTIVAR
    max_image_bytes: int = MAX_IMAGE_BYTES


def load_settings() -> Settings:
    """Build settings from defaults plus environment overrides."""
    overrides: dict = {}
    if os.environ.get("CV_MODEL_PATH"):
        overrides["model_path"] = Path(os.environ["CV_MODEL_PATH"])
    if os.environ.get("MATURITY_RATE_PER_DAY"):
        overrides["maturity_rate_per_day"] = float(os.environ["MATURITY_RATE_PER_DAY"])
    if os.environ.get("BANANA_FOREGROUND_MIN_RATIO"):
        overrides["banana_foreground_min_ratio"] = float(
            os.environ["BANANA_FOREGROUND_MIN_RATIO"]
        )
    return Settings(**overrides)
