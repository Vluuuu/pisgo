"""Configuration tests for detector runtime settings."""

from __future__ import annotations

from pathlib import Path

from app.config import load_settings


def test_detector_environment_overrides(monkeypatch):
    monkeypatch.setenv("DETECTOR_MODEL_PATH", "D:/models/custom.pt")
    monkeypatch.setenv("DETECTOR_MODEL_VERSION", "custom-detector")
    monkeypatch.setenv("DETECTOR_CONFIDENCE_THRESHOLD", "0.4")

    settings = load_settings()

    assert settings.detector_path == Path("D:/models/custom.pt")
    assert settings.detector_model_version == "custom-detector"
    assert settings.detector_confidence_threshold == 0.4
