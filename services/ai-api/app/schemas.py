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
    """Raw detector and maturity-model output for traceability."""

    predicted_class: Optional[str] = Field(
        default=None,
        description="Raw argmax class; null when detection short-circuits maturity inference.",
    )
    class_probabilities: Optional[dict[str, float]] = Field(
        default=None,
        description="Raw class probabilities; null when no banana is detected.",
    )
    maturity_class_scale: Optional[dict[str, float]] = Field(
        default=None,
        description="PisGo class-to-scale mapping; null when no banana is detected.",
    )
    detector_model_version: str
    detection_score: Optional[float] = Field(default=None, ge=0, le=1)
    detection_count: int = Field(ge=0)
    detection_threshold: float = Field(ge=0, le=1)
    detection_method: str = "yolo11n-class-0"
    detector_inference_milliseconds: Optional[float] = Field(default=None, ge=0)
    inference_milliseconds: Optional[float] = Field(default=None, ge=0)


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
