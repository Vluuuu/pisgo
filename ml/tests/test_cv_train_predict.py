from __future__ import annotations

import json
from pathlib import Path

import yaml

from pisgo_ml.cv_predict import load_cv_artifact, predict_archive_member
from pisgo_ml.cv_train import train_cv_from_config
from test_cv_data import LABEL_COLORS, make_tiny_cv_zip


def test_cv_training_persists_artifact_and_predicts_raw_output(tmp_path):
    archive = make_tiny_cv_zip(tmp_path / "tiny.zip")
    config = {
        "project": {
            "name": "tiny-cv",
            "model_version": "tiny-cv-v1",
            "random_seed": 3,
        },
        "paths": {
            "dataset_zip": str(archive),
            "manifest_output": str(tmp_path / "manifest.csv"),
            "model_output": str(tmp_path / "model.joblib"),
            "metrics_output": str(tmp_path / "metrics.json"),
            "prediction_output": str(tmp_path / "prediction.json"),
        },
        "data": {
            "variety": "Cavendish",
            "labels": [label.lower() for label in LABEL_COLORS],
            "train_ratio": 0.5,
            "validation_ratio": 0.25,
            "test_ratio": 0.25,
            "train_with_augmented": True,
        },
        "features": {
            "resize_width": 64,
            "resize_height": 48,
            "histogram_bins": 8,
            "grid_rows": 2,
            "grid_columns": 2,
        },
        "model": {"max_iter": 300, "c": 1.0, "class_weight": "balanced"},
    }
    config_path = tmp_path / "cv.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    artifact, metrics = train_cv_from_config(config_path)

    assert (tmp_path / "model.joblib").is_file()
    assert (tmp_path / "manifest.csv").is_file()
    assert json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))[
        "model_version"
    ] == "tiny-cv-v1"
    assert metrics["model"]["test"]["accuracy"] >= 0.75

    reloaded = load_cv_artifact(tmp_path / "model.joblib")
    member = "Dataset/Cavendish/Cavendish_Ripe_Top_0001.jpg"
    prediction = predict_archive_member(archive, member, reloaded)

    assert prediction["artifact_format"] == "pisgo_ml.cv.joblib"
    assert prediction["predicted_class"] in config["data"]["labels"]
    assert abs(sum(prediction["class_probabilities"].values()) - 1.0) < 1e-6
    assert 0 <= prediction["confidence"] <= 1
