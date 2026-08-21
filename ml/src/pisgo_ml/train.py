"""Train and persist the complete Cavendish tabular inference artifact."""

from __future__ import annotations

import argparse
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import sklearn
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

from .config import load_config
from .data import group_train_test_indices, load_dataset, prepare_training_data
from .evaluate import classification_metrics, regression_metrics
from .features import build_preprocessor
from .schema import ARRIVAL_TARGET, HARVEST_TARGET, READINESS_TARGET
from .utils import ensure_parent, write_json


def train_from_config(
    config_path: str | Path,
    data_path: str | Path | None = None,
    model_path: str | Path | None = None,
    metrics_path: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = load_config(config_path)
    source = Path(data_path) if data_path else config["paths"]["train_data"]
    destination = Path(model_path) if model_path else config["paths"]["model_output"]
    report_path = Path(metrics_path) if metrics_path else config["paths"]["metrics_output"]

    raw = load_dataset(source)
    target_config = config["data"]["target_columns"]
    inputs, targets = prepare_training_data(
        raw,
        harvest_column=target_config["harvest_date"],
        arrival_column=target_config["arrival_date"],
        readiness_column=target_config["readiness_status"],
    )

    train_index, test_index = group_train_test_indices(
        raw,
        group_column=config["data"]["group_column"],
        test_size=float(config["data"]["test_size"]),
        random_state=int(config["project"]["random_seed"]),
    )
    X_train = inputs.loc[train_index]
    X_test = inputs.loc[test_index]
    y_train = targets.loc[train_index]
    y_test = targets.loc[test_index]

    preprocessor = build_preprocessor()
    transformed_train = preprocessor.fit_transform(X_train)
    transformed_test = preprocessor.transform(X_test)

    seed = int(config["project"]["random_seed"])
    regression_params = dict(config["model"]["regression"])
    classification_params = dict(config["model"]["classification"])
    classification_enabled = bool(classification_params.pop("enabled", True))

    models: dict[str, Any] = {}
    metrics: dict[str, Any] = {
        "model_version": config["project"]["model_version"],
        "dataset": str(source),
        "rows": {"total": len(inputs), "train": len(X_train), "test": len(X_test)},
        "split": {
            "strategy": "group_shuffle_split",
            "group_column": config["data"]["group_column"],
            "test_size": float(config["data"]["test_size"]),
            "random_seed": seed,
        },
        "regression": {},
        "classification": None,
    }

    for target_name, artifact_prefix in [
        (HARVEST_TARGET, "harvest"),
        (ARRIVAL_TARGET, "arrival"),
    ]:
        baseline = DummyRegressor(strategy="median")
        baseline.fit(transformed_train, y_train[target_name])
        main_model = RandomForestRegressor(random_state=seed, **regression_params)
        main_model.fit(transformed_train, y_train[target_name])

        models[f"{artifact_prefix}_baseline"] = baseline
        models[artifact_prefix] = main_model
        metrics["regression"][artifact_prefix] = {
            "baseline": regression_metrics(
                y_test[target_name], baseline.predict(transformed_test)
            ),
            "model": regression_metrics(
                y_test[target_name], main_model.predict(transformed_test)
            ),
        }

    if classification_enabled and READINESS_TARGET in targets.columns:
        classification_train = y_train[READINESS_TARGET].notna()
        classification_test = y_test[READINESS_TARGET].notna()
        train_labels = y_train.loc[classification_train, READINESS_TARGET].astype(str)
        test_labels = y_test.loc[classification_test, READINESS_TARGET].astype(str)
        if train_labels.nunique() >= 2 and len(test_labels) > 0:
            classifier = RandomForestClassifier(random_state=seed, **classification_params)
            classifier.fit(transformed_train[classification_train.to_numpy()], train_labels)
            test_predictions = classifier.predict(
                transformed_test[classification_test.to_numpy()]
            )
            models["readiness"] = classifier
            metrics["classification"] = {
                "target": READINESS_TARGET,
                "classes": classifier.classes_.tolist(),
                **classification_metrics(test_labels, test_predictions),
            }
        else:
            metrics["classification"] = {
                "skipped": "At least two training classes and one labeled test row are required."
            }

    artifact = {
        "artifact_format": "pisgo_ml.joblib",
        "artifact_version": 1,
        "model_version": config["project"]["model_version"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "preprocessor": preprocessor,
        "models": models,
        "feature_names": preprocessor.get_feature_names_out().tolist(),
        "target_units": {
            HARVEST_TARGET: "calendar_days_from_photo_date",
            ARRIVAL_TARGET: "calendar_days_from_photo_date",
        },
        "training": {
            "source": str(source),
            "rows": metrics["rows"],
            "split": metrics["split"],
        },
        "runtime": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "pandas": pd.__version__,
            "joblib": joblib.__version__,
        },
        "metrics": metrics,
    }

    ensure_parent(destination)
    joblib.dump(artifact, destination, compress=3)
    write_json(metrics, report_path)
    return artifact, metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--data", help="Override training CSV path")
    parser.add_argument("--model-output", help="Override Joblib output path")
    parser.add_argument("--metrics-output", help="Override metrics JSON path")
    args = parser.parse_args()

    artifact, metrics = train_from_config(
        args.config, args.data, args.model_output, args.metrics_output
    )
    print(f"Saved model artifact: {args.model_output or load_config(args.config)['paths']['model_output']}")
    print(f"Model version: {artifact['model_version']}")
    print(f"Rows: {metrics['rows']}")


if __name__ == "__main__":
    main()
