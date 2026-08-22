"""Shared fixtures for the PisGo AI adapter tests."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
ML_SRC = REPO_ROOT / "ml" / "src"

for path in (str(SERVICE_ROOT), str(ML_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

MODEL_PATH = REPO_ROOT / "ml" / "models" / "cavendish_maturity_classifier.joblib"


@pytest.fixture(scope="session")
def banana_image_bytes() -> bytes:
    """A deterministic banana-like image generated entirely in memory."""
    image = Image.new("RGB", (640, 480), (235, 235, 230))
    draw = ImageDraw.Draw(image)
    draw.ellipse((120, 100, 520, 380), fill=(230, 190, 25), outline=(130, 100, 20), width=8)
    draw.rectangle((300, 70, 340, 115), fill=(100, 80, 20))
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=95)
    return buf.getvalue()


@pytest.fixture(scope="session")
def blank_image_bytes() -> bytes:
    """A uniform gray image with no banana-like pixels."""
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (128, 128, 128)).save(buf, "JPEG")
    return buf.getvalue()
