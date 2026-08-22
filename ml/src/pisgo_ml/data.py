"""CSV loading, schema validation, target creation, and leakage-safe splitting."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from .schema import (
    ARRIVAL_TARGET,
    DATE_COLUMNS,
    HARVEST_TARGET,
    MODEL_INPUT_COLUMNS,
    READINESS_TARGET,
    REQUIRED_INPUT_COLUMNS,
)


class DatasetValidationError(ValueError):
    """Raised when a CSV does not satisfy the expected dataset contract."""


def load_dataset(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Dataset not found: {source}")
    frame = pd.read_csv(source)
    if frame.empty:
        raise DatasetValidationError(f"Dataset is empty: {source}")
    return frame


def validate_columns(frame: pd.DataFrame, required: Iterable[str]) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise DatasetValidationError(f"Missing required columns: {', '.join(missing)}")


def parse_date_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in DATE_COLUMNS:
        if column not in result.columns:
            continue
        original = result[column]
        parsed = pd.to_datetime(original, errors="coerce")
        invalid = original.notna() & parsed.isna()
        if invalid.any():
            rows = ", ".join(str(index) for index in result.index[invalid][:5])
            raise DatasetValidationError(f"Invalid date in '{column}' at row(s): {rows}")
        result[column] = parsed
    return result


def prepare_inputs(frame: pd.DataFrame) -> pd.DataFrame:
    validate_columns(frame, REQUIRED_INPUT_COLUMNS)
    result = parse_date_columns(frame)

    for column in MODEL_INPUT_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA

    for column in ["plant_id", "bunch_id"]:
        if result[column].isna().any():
            raise DatasetValidationError(f"Column '{column}' cannot contain missing values")

    chronology_errors = (
        (result["flowering_date"] < result["planting_date"])
        | (result["photo_date"] < result["flowering_date"])
    )
    if chronology_errors.any():
        rows = ", ".join(str(index) for index in result.index[chronology_errors][:5])
        raise DatasetValidationError(
            "Expected planting_date <= flowering_date <= photo_date; "
            f"invalid row(s): {rows}"
        )

    return result


def prepare_training_data(
    frame: pd.DataFrame,
    harvest_column: str = "harvest_date",
    arrival_column: str = "arrival_date",
    readiness_column: str = READINESS_TARGET,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    validate_columns(frame, [*REQUIRED_INPUT_COLUMNS, harvest_column, arrival_column])
    prepared = prepare_inputs(frame)

    for target_date in [harvest_column, arrival_column]:
        if target_date not in prepared.columns:
            prepared[target_date] = pd.to_datetime(frame[target_date], errors="coerce")

    if prepared[[harvest_column, arrival_column]].isna().any().any():
        raise DatasetValidationError("harvest_date and arrival_date cannot be missing for training")

    harvest_days = (prepared[harvest_column] - prepared["photo_date"]).dt.days
    arrival_days = (prepared[arrival_column] - prepared["photo_date"]).dt.days
    invalid = (harvest_days < 0) | (arrival_days < harvest_days)
    if invalid.any():
        rows = ", ".join(str(index) for index in prepared.index[invalid][:5])
        raise DatasetValidationError(
            "Expected photo_date <= harvest_date <= arrival_date; "
            f"invalid row(s): {rows}"
        )

    targets = pd.DataFrame(
        {
            HARVEST_TARGET: harvest_days.astype(float),
            ARRIVAL_TARGET: arrival_days.astype(float),
        },
        index=prepared.index,
    )
    if readiness_column in frame.columns:
        targets[READINESS_TARGET] = frame[readiness_column].astype("string")

    return prepared[MODEL_INPUT_COLUMNS].copy(), targets


def group_train_test_indices(
    frame: pd.DataFrame,
    group_column: str,
    test_size: float,
    random_state: int,
) -> tuple[pd.Index, pd.Index]:
    if group_column not in frame.columns:
        raise DatasetValidationError(f"Group column not found: {group_column}")
    if not 0 < test_size < 1:
        raise DatasetValidationError("test_size must be between 0 and 1")
    if frame[group_column].nunique(dropna=True) < 2:
        raise DatasetValidationError(
            f"At least two distinct '{group_column}' values are required for group splitting"
        )

    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    train_positions, test_positions = next(
        splitter.split(frame, groups=frame[group_column].astype(str))
    )
    return frame.index[train_positions], frame.index[test_positions]
