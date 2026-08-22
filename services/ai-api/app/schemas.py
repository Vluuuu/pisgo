"""Request/response models for the PisGo AI adapter API.

The response is a superset of shared/schemas/prediction.schema.json:
every schema-required field is present with matching types; the `debug`
object carries raw classifier output so the 4-class result stays
traceable and is never erased by the 1-7 mapping.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PredictionDebug(BaseModel):
    """Raw model output and adapter internals, for traceability/debugging."""

    predicted_class: str = Field(
        description="Raw argmax class from the 4-class CV classifier."
    )
    class_probabilities: dict[str, float] = Field(
        description="Raw per-class probabilities from the classifier."
    )
    maturity_class_scale: dict[str, float] = Field(
        description="PisGo design mapping from class to UI scale 1-7 (not calibrated)."
    )
    foreground_proxy_ratio: float = Field(
        description="Share of banana-like pixels; basis of the detection heuristic."
    )
    banana_detection_threshold: float = Field(
        description="Heuristic threshold applied to foreground_proxy_ratio."
    )
    detection_method: str = Field(
        default="foreground-color-heuristic-proxy",
        description="Detection is a color heuristic proxy, not a trained detector.",
    )
    inference_milliseconds: Optional[float] = None


class PredictionResponse(BaseModel):
    banana_detected: bool
    cultivar: str
    days_after_flowering: int = Field(ge=0)
    current_maturity: Optional[float] = Field(
        default=None,
        description="Probability-weighted blend of the class->scale design mapping. "
        "Null when banana_detected is false (never a fabricated maturity).",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description="Uncalibrated classifier confidence score. Null when banana_detected is false.",
    )
    days_to_target: Optional[float] = Field(
        default=None,
        description="Linear-heuristic estimate; null when already past target or no banana detected.",
    )
    model_version: str
    adapter_version: str
    debug: PredictionDebug


class ErrorResponse(BaseModel):
    error: str


class HealthResponse(BaseModel):
    status: str
    model_version: str
    adapter_version: str
    model_loaded: bool
