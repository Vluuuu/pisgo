"""Unit tests for the PisGo adapter logic (pure functions)."""

from __future__ import annotations

from datetime import date

import pytest

from app.adapter import (
    compute_days_after_flowering,
    estimate_days_to_target,
    weighted_maturity,
)
from app.config import MATURITY_CLASS_SCALE


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
