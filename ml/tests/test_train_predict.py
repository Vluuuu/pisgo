from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from pisgo_ml.predict import load_artifact, predict_csv
from pisgo_ml.synthetic import generate_synthetic_dataset
from pisgo_ml.train import train_from_config


def _write_test_config(tmp_path: Path, data_path: Path) -> Path:
    config = {
        "project": {
            "name": "test-predictor",
            "model_version": "test-v1",
            "random_seed": 7,
        },
        "paths": {
            "train_data": str(data_path),
            "prediction_input": str(data_path),
            "model_output": str(tmp_path / "model.joblib"),
            "metrics_output": str(tmp_path / "metrics.json"),
            "evaluation_output": str(tmp_path / "evaluation.json"),
            "predictions_output": str(tmp_path / "predictions.csv"),
        },
        "data": {
            "group_column": "bunch_id",
            "test_size": 0.25,
            "required_input_columns": [
                "plant_id",
                "bunch_id",
                "planting_date",
                "flowering_date",
                "photo_date",
            ],
            "target_columns": {
                "harvest_date": "harvest_date",
                "arrival_date": "arrival_date",
                "readiness_status": "readiness_status",
            },
        },
        "model": {
            "regression": {
                "n_estimators": 12,
                "max_depth": 6,
                "min_samples_leaf": 1,
                "n_jobs": 1,
            },
            "classification": {
                "enabled": True,
                "n_estimators": 12,
                "max_depth": 6,
                "min_samples_leaf": 1,
                "n_jobs": 1,
            },
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_training_persists_complete_artifact_and_prediction_csv(tmp_path):
    data_path = tmp_path / "train.csv"
    generate_synthetic_dataset(rows=40, seed=9).to_csv(data_path, index=False)
    config_path = _write_test_config(tmp_path, data_path)

    artifact, metrics = train_from_config(config_path)
    model_path = tmp_path / "model.joblib"
    metrics_path = tmp_path / "metrics.json"

    assert model_path.is_file()
    assert metrics_path.is_file()
    assert artifact["artifact_format"] == "pisgo_ml.joblib"
    assert {"harvest", "arrival", "readiness"} <= set(artifact["models"])
    assert metrics["rows"]["total"] == 40
    assert json.loads(metrics_path.read_text(encoding="utf-8"))["model_version"] == "test-v1"

    input_path = tmp_path / "inference.csv"
    pd.read_csv(data_path).drop(
        columns=["harvest_date", "shipping_date", "arrival_date", "readiness_status"]
    ).head(5).to_csv(input_path, index=False)
    output_path = tmp_path / "predictions.csv"
    predictions = predict_csv(input_path, model_path, output_path)

    reloaded = load_artifact(model_path)
    assert reloaded["model_version"] == "test-v1"
    assert output_path.is_file()
    assert len(predictions) == 5
    assert predictions["predicted_harvest_date"].notna().all()
    assert predictions["predicted_arrival_date"].notna().all()
    assert (
        predictions["predicted_arrival_days_from_photo"]
        >= predictions["predicted_harvest_days_from_photo"]
    ).all()
