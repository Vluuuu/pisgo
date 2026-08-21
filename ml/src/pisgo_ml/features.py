"""Feature engineering and scikit-learn preprocessing."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .schema import (
    MODEL_CATEGORICAL_COLUMNS,
    MODEL_INPUT_COLUMNS,
    MODEL_NUMERIC_COLUMNS,
    REQUIRED_INPUT_COLUMNS,
)


class CavendishFeatureEngineer(BaseEstimator, TransformerMixin):
    """Convert raw agronomy and logistics fields into model-ready features."""

    def fit(self, X: pd.DataFrame, y: object = None) -> "CavendishFeatureEngineer":
        self._validate_input(X)
        return self

    def get_feature_names_out(self, input_features: object = None) -> np.ndarray:
        return np.asarray(MODEL_NUMERIC_COLUMNS + MODEL_CATEGORICAL_COLUMNS, dtype=object)

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        self._validate_input(X)
        result = X.copy()
        for column in MODEL_INPUT_COLUMNS:
            if column not in result.columns:
                result[column] = pd.NA

        for column in ["planting_date", "flowering_date", "photo_date"]:
            result[column] = pd.to_datetime(result[column], errors="coerce")

        result["plant_age_days"] = (result["photo_date"] - result["planting_date"]).dt.days
        result["fruit_age_days"] = (result["photo_date"] - result["flowering_date"]).dt.days
        result["planting_to_flowering_days"] = (
            result["flowering_date"] - result["planting_date"]
        ).dt.days

        month = result["photo_date"].dt.month.astype(float)
        result["photo_month_sin"] = np.sin(2 * np.pi * month / 12)
        result["photo_month_cos"] = np.cos(2 * np.pi * month / 12)

        travel_hours = pd.to_numeric(result["travel_duration_hours"], errors="coerce")
        distance_km = pd.to_numeric(result["distance_km"], errors="coerce")
        temperature = pd.to_numeric(result["temperature_c"], errors="coerce")
        humidity = pd.to_numeric(result["humidity_pct"], errors="coerce")

        result["travel_duration_days"] = travel_hours / 24
        result["estimated_speed_kmh"] = distance_km / travel_hours.replace(0, np.nan)
        result["temperature_humidity_index"] = temperature * (humidity / 100)

        for column in MODEL_NUMERIC_COLUMNS:
            result[column] = pd.to_numeric(result[column], errors="coerce")
        for column in MODEL_CATEGORICAL_COLUMNS:
            result[column] = result[column].astype("string")

        return result[MODEL_NUMERIC_COLUMNS + MODEL_CATEGORICAL_COLUMNS]

    @staticmethod
    def _validate_input(X: pd.DataFrame) -> None:
        if not isinstance(X, pd.DataFrame):
            raise TypeError("CavendishFeatureEngineer expects a pandas DataFrame")
        missing = sorted(set(REQUIRED_INPUT_COLUMNS) - set(X.columns))
        if missing:
            raise ValueError(f"Missing required feature columns: {', '.join(missing)}")


def build_preprocessor() -> Pipeline:
    numeric_pipeline = Pipeline(
        [("imputer", SimpleImputer(strategy="median", keep_empty_features=True))]
    )
    categorical_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent", keep_empty_features=True)),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    columns = ColumnTransformer(
        [
            ("numeric", numeric_pipeline, MODEL_NUMERIC_COLUMNS),
            ("categorical", categorical_pipeline, MODEL_CATEGORICAL_COLUMNS),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    return Pipeline([("features", CavendishFeatureEngineer()), ("columns", columns)])
