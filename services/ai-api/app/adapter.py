"""PisGo adapter: raw CV classifier output -> PisGo prediction contract.

Responsibilities:
- gate banana presence with the frozen YOLO class-0 detector;
- run maturity inference only after a banana detection, using the original bytes;
- map the 4-class probabilities onto the PisGo 1-7 UI maturity scale;
- preserve detector and maturity-model outputs in the debug payload.

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
from .detector import BananaBunchDetector
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

    def __init__(
        self,
        artifact: dict,
        detector: BananaBunchDetector,
        settings: Settings,
    ):
        self.artifact = artifact
        self.detector = detector
        self.settings = settings

    @property
    def model_version(self) -> str:
        return str(self.artifact["model_version"])

    def predict(
        self,
        *,
        image_bytes: bytes,
        flowering_date: date,
        photo_date: date,
        target_maturity: float,
    ) -> PredictionResponse:
        days_after_flowering = compute_days_after_flowering(flowering_date, photo_date)

        detection = self.detector.predict(image_bytes)
        banana_detected = detection.detected

        if not banana_detected:
            debug = PredictionDebug(
                predicted_class=None,
                class_probabilities=None,
                maturity_class_scale=None,
                detector_model_version=self.detector.model_version,
                detection_score=None,
                detection_count=0,
                detection_threshold=self.detector.confidence_threshold,
                detection_method="yolo11n-class-0",
                detector_inference_milliseconds=detection.inference_milliseconds,
                inference_milliseconds=None,
            )
            return PredictionResponse(
                banana_detected=False,
                cultivar=self.settings.cultivar,
                days_after_flowering=days_after_flowering,
                current_maturity=None,
                confidence=None,
                days_to_target=None,
                model_version=self.model_version,
                adapter_version=self.settings.adapter_version,
                debug=debug,
            )

        raw = predict_image_source(
            io.BytesIO(image_bytes),
            self.artifact,
            input_reference="upload:image",
        )
        predicted_class = str(raw["predicted_class"])
        class_probabilities = {
            str(k): float(v) for k, v in raw["class_probabilities"].items()
        }

        debug = PredictionDebug(
            predicted_class=predicted_class,
            class_probabilities=class_probabilities,
            maturity_class_scale=dict(self.settings.maturity_class_scale),
            detector_model_version=self.detector.model_version,
            detection_score=detection.max_score,
            detection_count=detection.detection_count,
            detection_threshold=self.detector.confidence_threshold,
            detection_method="yolo11n-class-0",
            detector_inference_milliseconds=detection.inference_milliseconds,
            inference_milliseconds=raw.get("inference_milliseconds"),
        )

        current_maturity = round(
            weighted_maturity(class_probabilities, self.settings.maturity_class_scale),
            3,
        )
        return PredictionResponse(
            banana_detected=True,
            cultivar=self.settings.cultivar,
            days_after_flowering=days_after_flowering,
            current_maturity=current_maturity,
            confidence=round(float(raw["confidence"]), 4),
            days_to_target=estimate_days_to_target(
                current_maturity,
                target_maturity,
                self.settings.maturity_rate_per_day,
            ),
            model_version=self.model_version,
            adapter_version=self.settings.adapter_version,
            debug=debug,
        )
