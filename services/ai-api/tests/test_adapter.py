"""Unit tests for the PisGo adapter logic (pure functions)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

import app.adapter as adapter
from app.adapter import (
    BananaPredictor,
    compute_days_after_flowering,
    estimate_days_to_target,
    weighted_maturity,
)
from app.config import MATURITY_CLASS_SCALE, Settings
from app.detector import DetectionResult


class TestDaysAfterFlowering:
    def test_normal_delta(self):
        assert compute_days_after_flowering(date(2026, 8, 1), date(2026, 8, 22)) == 21

    def test_same_day_is_zero(self):
        assert compute_days_after_flowering(date(2026, 8, 22), date(2026, 8, 22)) == 0

    def test_negative_delta_clamped_to_zero(self):
        assert compute_days_after_flowering(date(2026, 8, 22), date(2026, 8, 1)) == 0


class TestWeightedMaturity:
    def test_single_class_gives_anchor_value(self):
        probs = {"unripe": 1.0, "half_ripe": 0.0, "ripe": 0.0, "overripe": 0.0}
        assert weighted_maturity(probs, MATURITY_CLASS_SCALE) == pytest.approx(2.0)

    def test_mixture_is_probability_weighted(self):
        probs = {"unripe": 0.0, "half_ripe": 0.5, "ripe": 0.5, "overripe": 0.0}
        assert weighted_maturity(probs, MATURITY_CLASS_SCALE) == pytest.approx(4.5)

    def test_unnormalized_probabilities_are_normalized(self):
        probs = {"ripe": 2.0, "overripe": 2.0}
        assert weighted_maturity(probs, MATURITY_CLASS_SCALE) == pytest.approx(6.0)

    def test_unknown_classes_are_ignored(self):
        probs = {"ripe": 1.0, "mystery_class": 5.0}
        assert weighted_maturity(probs, MATURITY_CLASS_SCALE) == pytest.approx(5.5)

    def test_zero_total_returns_zero(self):
        assert weighted_maturity({}, MATURITY_CLASS_SCALE) == 0.0


class TestDaysToTarget:
    def test_linear_estimate(self):
        assert estimate_days_to_target(5.0, 6.5, 0.15) == pytest.approx(10.0)

    def test_already_at_target_returns_none(self):
        assert estimate_days_to_target(6.5, 6.5, 0.15) is None

    def test_past_target_returns_none(self):
        assert estimate_days_to_target(6.8, 5.5, 0.15) is None


class TestBananaPredictorGate:
    def test_no_detection_short_circuits_maturity_classifier(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            adapter,
            "predict_image_source",
            lambda *args, **kwargs: called.append(True) or {},
        )
        detector = SimpleNamespace(
            model_version="test-detector",
            confidence_threshold=0.25,
            predict=lambda b: DetectionResult(0, 0.0, 12.0),
        )
        predictor = BananaPredictor(
            {"model_version": "cv-v1"},
            detector,
            Settings(),
        )
        res = predictor.predict(
            image_bytes=b"fake",
            flowering_date=date(2026, 8, 1),
            photo_date=date(2026, 8, 22),
            target_maturity=5.0,
        )

        assert res.banana_detected is False
        assert res.current_maturity is None
        assert res.confidence is None
        assert res.days_to_target is None
        assert res.debug.predicted_class is None
        assert res.debug.class_probabilities is None
        assert res.debug.detection_count == 0
        assert not called

    def test_detection_passes_original_bytes_to_maturity_classifier(self, monkeypatch):
        received_bytes = []

        def fake_predict_image_source(stream, artifact, input_reference=None):
            received_bytes.append(stream.read())
            return {
                "predicted_class": "ripe",
                "class_probabilities": {
                    "unripe": 0.0,
                    "half_ripe": 0.1,
                    "ripe": 0.9,
                    "overripe": 0.0,
                },
                "confidence": 0.9,
                "inference_milliseconds": 15.0,
            }

        monkeypatch.setattr(adapter, "predict_image_source", fake_predict_image_source)
        detector = SimpleNamespace(
            model_version="test-detector",
            confidence_threshold=0.25,
            predict=lambda b: DetectionResult(1, 0.85, 20.0),
        )
        predictor = BananaPredictor(
            {"model_version": "cv-v1"},
            detector,
            Settings(),
        )
        res = predictor.predict(
            image_bytes=b"exact-original-bytes",
            flowering_date=date(2026, 8, 1),
            photo_date=date(2026, 8, 22),
            target_maturity=6.0,
        )

        assert res.banana_detected is True
        assert res.current_maturity == pytest.approx(5.3)
        assert res.confidence == 0.9
        assert received_bytes == [b"exact-original-bytes"]
        assert res.debug.detection_count == 1
        assert res.debug.detection_score == 0.85
