from __future__ import annotations

import numpy as np

from pisgo_ml.data import prepare_training_data
from pisgo_ml.features import CavendishFeatureEngineer, build_preprocessor
from pisgo_ml.synthetic import generate_synthetic_dataset


def test_feature_engineering_calculates_ages_and_logistics():
    inputs, _ = prepare_training_data(generate_synthetic_dataset(rows=12))
    engineered = CavendishFeatureEngineer().fit_transform(inputs)

    assert engineered.loc[0, "plant_age_days"] > engineered.loc[0, "fruit_age_days"]
    assert engineered.loc[0, "fruit_age_days"] >= 0
    assert engineered.loc[0, "travel_duration_days"] > 0
    assert engineered.loc[0, "estimated_speed_kmh"] > 0


def test_preprocessor_imputes_missing_and_encodes_categories():
    inputs, _ = prepare_training_data(generate_synthetic_dataset(rows=16))
    transformed = build_preprocessor().fit_transform(inputs)

    assert transformed.shape[0] == len(inputs)
    assert transformed.shape[1] > 20
    assert np.isfinite(transformed).all()
