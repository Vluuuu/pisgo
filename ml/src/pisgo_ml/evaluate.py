"""Evaluate a persisted artifact against a labeled CSV without retraining."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)

from .config import load_config
from .data import load_dataset, prepare_training_data
from .utils import write_json


def regression_metrics(y_true: Any, y_pred: Any) -> dict[str, float | None]:
    true = np.asarray(y_true, dtype=float)
    predicted = np.asarray(y_pred, dtype=float)
    r2 = float(r2_score(true, predicted)) if len(true) >= 2 else None
    return {
        "mae_days": float(mean_absolute_error(true, predicted)),
        "rmse_days": float(math.sqrt(mean_squared_error(true, predicted))),
        "r2": r2,
    }


def classification_metrics(y_true: Any, y_pred: Any) -> dict[str, float]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_weighted": float(
            precision_score(y_true, y_pred, average="weighted", zero_division=0)
        ),
        "recall_weighted": float(
            recall_score(y_true, y_pred, average="weighted", zero_division=0)
        ),
        "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
    }


def evaluate_artifact(
    config_path: str | Path,
    data_path: str | Path | None = None,
    model_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    from .predict import load_artifact

    config = load_config(config_path)
    source = Path(data_path) if data_path else config["paths"]["train_data"]
    artifact_path = Path(model_path) if model_path else config["paths"]["model_output"]
    destination = Path(output_path) if output_path else config["paths"]["evaluation_output"]
    target_config = config["data"]["target_columns"]

    inputs, targets = prepare_training_data(
        load_dataset(source),
        harvest_column=target_config["harvest_date"],
        arrival_column=target_config["arrival_date"],
        readiness_column=target_config["readiness_status"],
    )
    artifact = load_artifact(artifact_path)
    transformed = artifact["preprocessor"].transform(inputs)
    models = artifact["models"]

    report: dict[str, Any] = {
        "model_version": artifact["model_version"],
        "artifact": str(artifact_path),
        "dataset": str(source),
        "rows": len(inputs),
        "note": "Metrics are computed on the provided labeled dataset; use held-out data for unbiased reporting.",
        "regression": {
            "harvest": regression_metrics(
                targets["harvest_days_from_photo"], models["harvest"].predict(transformed)
            ),
            "arrival": regression_metrics(
                targets["arrival_days_from_photo"], models["arrival"].predict(transformed)
            ),
        },
        "classification": None,
    }
    if "readiness" in models and "readiness_status" in targets.columns:
        labeled = targets["readiness_status"].notna()
        report["classification"] = classification_metrics(
            targets.loc[labeled, "readiness_status"].astype(str),
            models["readiness"].predict(transformed[labeled.to_numpy()]),
        )

    write_json(report, destination)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--data")
    parser.add_argument("--model")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = evaluate_artifact(args.config, args.data, args.model, args.output)
    print(f"Evaluated {report['rows']} rows with model {report['model_version']}")


if __name__ == "__main__":
    main()
