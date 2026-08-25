"""Small runtime wrapper for the frozen banana-bunch YOLO checkpoint."""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PIL import Image, UnidentifiedImageError


class DetectorError(RuntimeError):
    """Raised when the detector cannot load or run inference."""


class DetectorImageError(DetectorError):
    """Raised when detector input is not a readable image."""


@dataclass(frozen=True)
class DetectionResult:
    detection_count: int
    max_score: float
    inference_milliseconds: float

    @property
    def detected(self) -> bool:
        return self.detection_count > 0


def _ultralytics_yolo() -> Callable[[str], Any]:
    try:
        from ultralytics import YOLO
    except ImportError as error:
        raise DetectorError(
            "Ultralytics is not installed; install the pinned AI API dependencies."
        ) from error
    return YOLO


def _confidence_scores(result: Any) -> list[float]:
    confidence = getattr(getattr(result, "boxes", None), "conf", None)
    if confidence is None:
        return []
    if hasattr(confidence, "cpu"):
        confidence = confidence.cpu()
    if hasattr(confidence, "tolist"):
        confidence = confidence.tolist()
    return [float(value) for value in confidence]


class BananaBunchDetector:
    """Loads one checkpoint and reports class-0 detections at a fixed threshold."""

    def __init__(
        self,
        checkpoint: Path,
        *,
        model_version: str,
        confidence_threshold: float,
        model_factory: Callable[[str], Any] | None = None,
    ) -> None:
        if not checkpoint.is_file():
            raise DetectorError(f"Detector checkpoint not found: {checkpoint}")
        if not 0 < confidence_threshold <= 1:
            raise DetectorError("Detector confidence threshold must be in (0, 1].")
        try:
            self._model = (model_factory or _ultralytics_yolo())(str(checkpoint))
        except DetectorError:
            raise
        except Exception as error:
            raise DetectorError(f"Could not load detector checkpoint: {error}") from error
        self.model_version = model_version
        self.confidence_threshold = confidence_threshold

    def predict(self, image_bytes: bytes) -> DetectionResult:
        if not image_bytes:
            raise DetectorImageError("Detector input image is empty.")
        started = time.perf_counter()
        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                image = source.convert("RGB")
        except (UnidentifiedImageError, OSError) as error:
            raise DetectorImageError(f"Unreadable detector image: {error}") from error

        try:
            results = self._model.predict(
                source=image,
                conf=self.confidence_threshold,
                iou=0.70,
                imgsz=640,
                device="cpu",
                classes=[0],
                verbose=False,
            )
        except Exception as error:
            raise DetectorError(f"Detector inference failed: {error}") from error
        if not results:
            raise DetectorError("Detector returned no image result.")
        scores = _confidence_scores(results[0])
        return DetectionResult(
            detection_count=len(scores),
            max_score=max(scores, default=0.0),
            inference_milliseconds=round((time.perf_counter() - started) * 1000, 3),
        )
