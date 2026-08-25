"""Unit tests for the frozen YOLO runtime wrapper."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.detector import BananaBunchDetector, DetectorError, DetectorImageError


def test_detector_uses_frozen_threshold_and_class_zero(tmp_path, banana_image_bytes):
    checkpoint = tmp_path / "detector.pt"
    checkpoint.write_bytes(b"weights")
    calls = []

    class FakeModel:
        def predict(self, **kwargs):
            calls.append(kwargs)
            return [SimpleNamespace(boxes=SimpleNamespace(conf=[0.8, 0.6]))]

    detector = BananaBunchDetector(
        checkpoint,
        model_version="banana-bunch-yolo11n-v1",
        confidence_threshold=0.25,
        model_factory=lambda path: FakeModel(),
    )
    result = detector.predict(banana_image_bytes)

    assert result.detection_count == 2
    assert result.max_score == pytest.approx(0.8)
    assert result.detected is True
    assert result.inference_milliseconds >= 0
    assert calls[0]["conf"] == 0.25
    assert calls[0]["classes"] == [0]
    assert calls[0]["device"] == "cpu"


def test_detector_reports_no_detection(tmp_path, blank_image_bytes):
    checkpoint = tmp_path / "detector.pt"
    checkpoint.write_bytes(b"weights")
    model = SimpleNamespace(
        predict=lambda **kwargs: [SimpleNamespace(boxes=SimpleNamespace(conf=[]))]
    )
    detector = BananaBunchDetector(
        checkpoint,
        model_version="test",
        confidence_threshold=0.25,
        model_factory=lambda path: model,
    )

    result = detector.predict(blank_image_bytes)

    assert result.detected is False
    assert result.detection_count == 0
    assert result.max_score == 0.0


def test_detector_fails_closed_when_checkpoint_is_missing(tmp_path):
    with pytest.raises(DetectorError, match="checkpoint not found"):
        BananaBunchDetector(
            tmp_path / "missing.pt",
            model_version="test",
            confidence_threshold=0.25,
            model_factory=lambda path: object(),
        )


def test_detector_rejects_invalid_image(tmp_path):
    checkpoint = tmp_path / "detector.pt"
    checkpoint.write_bytes(b"weights")
    detector = BananaBunchDetector(
        checkpoint,
        model_version="test",
        confidence_threshold=0.25,
        model_factory=lambda path: SimpleNamespace(predict=lambda **kwargs: []),
    )

    with pytest.raises(DetectorImageError, match="Unreadable detector image"):
        detector.predict(b"not-an-image")
