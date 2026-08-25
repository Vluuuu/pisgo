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

# MVP biological-age normalization window, not a field-calibrated harvest claim.
EXPECTED_FLOWERING_TO_HARVEST_DAYS: int = 120

DETECTOR_MODEL_VERSION: str = "banana-bunch-yolo11n-emergency-v1"
DETECTOR_CONFIDENCE_THRESHOLD: float = 0.25

ADAPTER_VERSION: str = "pisgo-ai-api-v1"

CULTIVAR: str = "cavendish"

MAX_IMAGE_BYTES: int = 10 * 1024 * 1024


def _default_model_path() -> Path:
    return REPO_ROOT / "ml" / "models" / "cavendish_maturity_classifier.joblib"


def _default_detector_path() -> Path:
    return REPO_ROOT / "ml" / "models" / "banana_bunch_yolo11n_emergency_v1.pt"


def _load_class_scale() -> dict[str, float]:
    raw = os.environ.get("MATURITY_CLASS_SCALE_JSON")
    if not raw:
        return dict(MATURITY_CLASS_SCALE)
    parsed = json.loads(raw)
    return {str(k): float(v) for k, v in parsed.items()}


@dataclass(frozen=True)
class Settings:
    model_path: Path = field(default_factory=_default_model_path)
    detector_path: Path = field(default_factory=_default_detector_path)
    detector_model_version: str = DETECTOR_MODEL_VERSION
    detector_confidence_threshold: float = DETECTOR_CONFIDENCE_THRESHOLD
    maturity_class_scale: dict[str, float] = field(default_factory=_load_class_scale)
    maturity_rate_per_day: float = MATURITY_RATE_PER_DAY
    expected_flowering_to_harvest_days: int = EXPECTED_FLOWERING_TO_HARVEST_DAYS
    adapter_version: str = ADAPTER_VERSION
    cultivar: str = CULTIVAR
    max_image_bytes: int = MAX_IMAGE_BYTES


def load_settings() -> Settings:
    """Build settings from defaults plus environment overrides."""
    overrides: dict = {}
    if os.environ.get("CV_MODEL_PATH"):
        overrides["model_path"] = Path(os.environ["CV_MODEL_PATH"])
    if os.environ.get("DETECTOR_MODEL_PATH"):
        overrides["detector_path"] = Path(os.environ["DETECTOR_MODEL_PATH"])
    if os.environ.get("DETECTOR_MODEL_VERSION"):
        overrides["detector_model_version"] = os.environ["DETECTOR_MODEL_VERSION"]
    if os.environ.get("DETECTOR_CONFIDENCE_THRESHOLD"):
        overrides["detector_confidence_threshold"] = float(
            os.environ["DETECTOR_CONFIDENCE_THRESHOLD"]
        )
    if os.environ.get("MATURITY_RATE_PER_DAY"):
        overrides["maturity_rate_per_day"] = float(os.environ["MATURITY_RATE_PER_DAY"])
    if os.environ.get("EXPECTED_FLOWERING_TO_HARVEST_DAYS"):
        overrides["expected_flowering_to_harvest_days"] = int(
            os.environ["EXPECTED_FLOWERING_TO_HARVEST_DAYS"]
        )
    return Settings(**overrides)
