from __future__ import annotations

import pandas as pd
import pytest

from pisgo_ml.data import (
    DatasetValidationError,
    group_train_test_indices,
    load_dataset,
    prepare_training_data,
)
from pisgo_ml.synthetic import generate_synthetic_dataset


def test_loading_and_target_creation(tmp_path):
    source = tmp_path / "sample.csv"
    generate_synthetic_dataset(rows=20).to_csv(source, index=False)

    loaded = load_dataset(source)
    inputs, targets = prepare_training_data(loaded)

    assert len(inputs) == 20
    assert targets["harvest_days_from_photo"].ge(0).all()
    assert targets["arrival_days_from_photo"].ge(
        targets["harvest_days_from_photo"]
    ).all()
    assert "readiness_status" in targets


def test_validation_rejects_missing_required_column():
    frame = generate_synthetic_dataset(rows=12).drop(columns="photo_date")
    with pytest.raises(DatasetValidationError, match="photo_date"):
        prepare_training_data(frame)


def test_group_split_keeps_bunches_separate():
    frame = generate_synthetic_dataset(rows=24)
    train_index, test_index = group_train_test_indices(frame, "bunch_id", 0.25, 42)

    train_groups = set(frame.loc[train_index, "bunch_id"])
    test_groups = set(frame.loc[test_index, "bunch_id"])
    assert train_groups.isdisjoint(test_groups)
    assert len(train_index) + len(test_index) == len(frame)
