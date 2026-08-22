"""API-level tests for POST /v1/predict using FastAPI TestClient."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from app.config import MATURITY_CLASS_SCALE
from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "shared" / "schemas" / "prediction.schema.json"

pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / "ml" / "models" / "cavendish_maturity_classifier.joblib").is_file(),
    reason="CV model artifact not present (intentionally excluded from Git)",
)

client = TestClient(app)

FORM = {
    "flowering_date": "2026-08-01",
    "photo_date": "2026-08-22",
    "target_maturity": "6.5",
}

SCHEMA_REQUIRED = [
    "banana_detected",
    "cultivar",
    "days_after_flowering",
    "current_maturity",
    "confidence",
    "model_version",
]


def _post(image_bytes: bytes, filename: str = "photo.jpg", **form_overrides):
    form = {**FORM, **{k: str(v) for k, v in form_overrides.items()}}
    return client.post(
        "/v1/predict",
        data=form,
        files={"image": (filename, image_bytes, "image/jpeg")},
    )


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_loaded"] is True
    assert body["status"] == "ok"
    assert body["model_version"] == "cavendish-color-texture-v1"


class TestBananaDetected:
    def test_detected_response_shape(self, banana_image_bytes):
        resp = _post(banana_image_bytes)
        assert resp.status_code == 200
        body = resp.json()

        # All schema-required fields present with right types
        for field_name in SCHEMA_REQUIRED:
            assert field_name in body, f"missing required field {field_name}"
        assert body["banana_detected"] is True
        assert body["cultivar"] == "cavendish"
        assert body["days_after_flowering"] == 21
        assert isinstance(body["current_maturity"], (int, float))
        assert 1 <= body["current_maturity"] <= 7
        assert 0 <= body["confidence"] <= 1
        assert body["model_version"] == "cavendish-color-texture-v1"
        assert "days_to_target" in body

    def test_raw_class_output_preserved_in_debug(self, banana_image_bytes):
        body = _post(banana_image_bytes).json()
        debug = body["debug"]
        assert debug["predicted_class"] in MATURITY_CLASS_SCALE
        probs = debug["class_probabilities"]
        assert set(probs) == set(MATURITY_CLASS_SCALE)
        assert sum(probs.values()) == pytest.approx(1.0, abs=1e-4)
        # The mapping table itself is echoed back for traceability
        assert debug["maturity_class_scale"] == MATURITY_CLASS_SCALE

    def test_current_maturity_matches_weighted_mapping(self, banana_image_bytes):
        body = _post(banana_image_bytes).json()
        probs = body["debug"]["class_probabilities"]
        expected = sum(MATURITY_CLASS_SCALE[c] * probs[c] for c in probs)
        assert body["current_maturity"] == pytest.approx(expected, abs=1e-3)

    def test_days_to_target_linear(self, banana_image_bytes):
        body = _post(banana_image_bytes).json()
        if body["days_to_target"] is not None:
            expected = round((6.5 - body["current_maturity"]) / 0.15, 2)
            assert body["days_to_target"] == pytest.approx(expected, abs=0.01)


class TestNoBanana:
    def test_no_fabricated_maturity(self, blank_image_bytes):
        resp = _post(blank_image_bytes, filename="blank.jpg")
        assert resp.status_code == 200
        body = resp.json()
        assert body["banana_detected"] is False
        # Explicit: no fake maturity/confidence/days_to_target
        assert body["current_maturity"] is None
        assert body["confidence"] is None
        assert body["days_to_target"] is None
        # Dates still computed honestly
        assert body["days_after_flowering"] == 21
        # Raw classifier output still available for debugging
        assert body["debug"]["predicted_class"] in MATURITY_CLASS_SCALE
        assert body["debug"]["foreground_proxy_ratio"] < body["debug"]["banana_detection_threshold"]


class TestValidation:
    def test_target_maturity_out_of_range(self, banana_image_bytes):
        resp = _post(banana_image_bytes, target_maturity=8)
        assert resp.status_code == 422

    def test_photo_before_flowering_rejected(self, banana_image_bytes):
        resp = _post(banana_image_bytes, photo_date="2026-07-01")
        assert resp.status_code == 422

    def test_empty_image_rejected(self):
        resp = _post(b"", filename="empty.jpg")
        assert resp.status_code == 400

    def test_corrupt_image_rejected(self):
        resp = _post(b"not-an-image", filename="x.jpg")
        assert resp.status_code == 400

    def test_missing_fields_rejected(self, banana_image_bytes):
        resp = client.post(
            "/v1/predict",
            files={"image": ("photo.jpg", banana_image_bytes, "image/jpeg")},
        )
        assert resp.status_code == 422


class TestContractCompliance:
    @pytest.mark.parametrize("fixture_name", ["banana_image_bytes", "blank_image_bytes"])
    def test_response_matches_shared_schema(self, request, fixture_name):
        schema = json.loads(SCHEMA_PATH.read_text())
        body = _post(request.getfixturevalue(fixture_name)).json()
        jsonschema.Draft202012Validator(schema).validate(body)
