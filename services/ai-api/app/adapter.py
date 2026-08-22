"""PisGo adapter: raw CV classifier output -> PisGo prediction contract.

Responsibilities:
- run raw inference via pisgo_ml.cv_predict (artifact is the source of truth
  for model_version, labels, preprocessing, and the feature pipeline);
- banana detection via a documented heuristic proxy (foreground color ratio);
- map the 4-class probabilities onto the PisGo 1-7 UI maturity scale using
  the configurable design mapping in config.py;
- keep the raw predicted_class + class_probabilities in the debug payload so
  any 1-7 number can be traced back to the underlying class probabilities.

Explicit non-goals / disclaimers:
- the class->scale mapping is a PisGo design decision, NOT an agronomic
  calibration;
- `confidence` is the classifier's uncalibrated max-class probability;
- `days_to_target` is a linear placeholder heuristic;
- when banana_detected=false the service returns NO fabricated maturity or
  confidence (those fields are null) while days_after_flowering is still
  computed from the supplied dates.
"""

from __future__ import annotations

import io
from datetime import date

from pisgo_ml.cv_predict import predict_image_source

from .config import Settings
from .schemas import PredictionDebug, PredictionResponse


def compute_days_after_flowering(flowering_date: date, photo_date: date) -> int:
    """Whole days between flowering and photo; negative deltas clamp to 0."""
    return max(0, (photo_date - flowering_date).days)


def weighted_maturity(
    class_probabilities: dict[str, float], scale: dict[str, float]
) -> float:
    """Probability-weighted blend of the class->scale design mapping.

    This is an adapter of visual class probabilities onto the PisGo 1-7 UI
    scale, not a measured maturity index.
    """
    total = sum(class_probabilities.get(cls, 0.0) for cls in scale)
    if total <= 0:
        return 0.0
    return sum(scale[cls] * class_probabilities.get(cls, 0.0) for cls in scale) / total


def estimate_days_to_target(
    current_maturity: float, target_maturity: float, rate_per_day: float
) -> float | None:
    """Linear placeholder estimate. None when already at/past target."""
    gap = target_maturity - current_maturity
    if gap <= 0:
        return None
    return round(gap / rate_per_day, 2)


class BananaPredictor:
    """Holds the loaded CV artifact and adapts its raw output for PisGo."""

    def __init__(self, artifact: dict, settings: Settings):
        self.artifact = artifact
        self.settings = settings
        self._extractor = artifact["feature_extractor"]
        self._feature_names = list(artifact["feature_names"])
        self._fg_index = self._feature_names.index("foreground_proxy_ratio")

    @property
    def model_version(self) -> str:
        return str(self.artifact["model_version"])

    def _foreground_proxy_ratio(self, image_bytes: bytes) -> float:
        features = self._extractor.transform([io.BytesIO(image_bytes)])
        return float(features[0, self._fg_index])

    def predict(
        self,
        *,
        image_bytes: bytes,
        flowering_date: date,
        photo_date: date,
        target_maturity: float,
    ) -> PredictionResponse:
        days_after_flowering = compute_days_after_flowering(flowering_date, photo_date)

        foreground_ratio = self._foreground_proxy_ratio(image_bytes)
        banana_detected = (
            foreground_ratio >= self.settings.banana_foreground_min_ratio
        )

        raw = predict_image_source(
            io.BytesIO(image_bytes), self.artifact, input_reference="upload:image"
        )
        predicted_class = str(raw["predicted_class"])
        class_probabilities = {
            str(k): float(v) for k, v in raw["class_probabilities"].items()
        }

        debug = PredictionDebug(
            predicted_class=predicted_class,
            class_probabilities=class_probabilities,
            maturity_class_scale=dict(self.settings.maturity_class_scale),
            foreground_proxy_ratio=round(foreground_ratio, 6),
            banana_detection_threshold=self.settings.banana_foreground_min_ratio,
            inference_milliseconds=raw.get("inference_milliseconds"),
        )

        base = dict(
            banana_detected=banana_detected,
            cultivar=self.settings.cultivar,
            days_after_flowering=days_after_flowering,
            model_version=self.model_version,
            adapter_version=self.settings.adapter_version,
            debug=debug,
        )

        if not banana_detected:
            # Explicit no-banana behavior: no fabricated maturity, confidence,
            # or days_to_target. Raw classifier output is still in debug.
            return PredictionResponse(
                current_maturity=None,
                confidence=None,
                days_to_target=None,
                **base,
            )

        current_maturity = round(
            weighted_maturity(class_probabilities, self.settings.maturity_class_scale),
            3,
        )
        return PredictionResponse(
            current_maturity=current_maturity,
            confidence=round(float(raw["confidence"]), 4),
            days_to_target=estimate_days_to_target(
                current_maturity,
                target_maturity,
                self.settings.maturity_rate_per_day,
            ),
            **base,
        )
