from __future__ import annotations

import io

import numpy as np
from PIL import Image

from pisgo_ml.cv_features import BananaImageFeatureExtractor


def test_image_features_are_deterministic_and_named():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 40), (220, 190, 30)).save(buffer, format="JPEG")
    source = buffer.getvalue()
    extractor = BananaImageFeatureExtractor(
        resize_width=64, resize_height=48, histogram_bins=8, grid_rows=2, grid_columns=2
    )

    first = extractor.extract(source)
    second = extractor.extract(source)

    assert first.ndim == 1
    assert len(first) == len(extractor.get_feature_names_out())
    assert np.allclose(first, second)
    assert np.isfinite(first).all()
