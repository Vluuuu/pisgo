"""Run inference from a persisted Joblib artifact without retraining."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .config import load_config
from .data import load_dataset, prepare_inputs
from .schema import ID_COLUMNS
from .utils import ensure_parent


class ArtifactError(ValueError):
    """Raised when a model artifact cannot be used for inference."""


def load_artifact(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(
            f"Model artifact not found: {source}. Run training before inference."
        )
    artifact = joblib.load(source)
    if not isinstance(artifact, dict) or artifact.get("artifact_format") != "pisgo_ml.joblib":
        raise ArtifactError(f"Unsupported model artifact: {source}")
    required = {"preprocessor", "models", "model_version"}
    missing = sorted(required - set(artifact))
    if missing:
        raise ArtifactError(f"Artifact is missing fields: {', '.join(missing)}")
    return artifact


def predict_frame(frame: pd.DataFrame, artifact: dict[str, Any]) -> pd.DataFrame:
    prepared = prepare_inputs(frame)
    transformed = artifact["preprocessor"].transform(prepared)
    models = artifact["models"]
    if "harvest" not in models or "arrival" not in models:
        raise ArtifactError("Artifact must contain harvest and arrival models")

    harvest_days_raw = np.asarray(models["harvest"].predict(transformed), dtype=float)
    arrival_days_raw = np.asarray(models["arrival"].predict(transformed), dtype=float)
    harvest_days = np.maximum(0, np.rint(harvest_days_raw)).astype(int)
    arrival_days = np.maximum(harvest_days, np.rint(arrival_days_raw).astype(int))
    photo_dates = pd.to_datetime(prepared["photo_date"])

    output = pd.DataFrame(index=frame.index)
    for column in ID_COLUMNS:
        if column in frame.columns:
            output[column] = frame[column]

    output["prediction_reference_date"] = photo_dates.dt.strftime("%Y-%m-%d")
    output["predicted_harvest_days_from_photo"] = harvest_days
    output["predicted_harvest_date"] = (
        photo_dates + pd.to_timedelta(harvest_days, unit="D")
    ).dt.strftime("%Y-%m-%d")
    output["predicted_arrival_days_from_photo"] = arrival_days
    output["predicted_arrival_date"] = (
        photo_dates + pd.to_timedelta(arrival_days, unit="D")
    ).dt.strftime("%Y-%m-%d")

    classifier = models.get("readiness")
    if classifier is not None:
        output["predicted_readiness_status"] = classifier.predict(transformed)
        probabilities = classifier.predict_proba(transformed)
        output["readiness_confidence"] = probabilities.max(axis=1).round(6)
    else:
        output["predicted_readiness_status"] = pd.NA
        output["readiness_confidence"] = pd.NA

    output["model_version"] = artifact["model_version"]
    return output


def predict_csv(
    input_path: str | Path,
    model_path: str | Path,
    output_path: str | Path,
) -> pd.DataFrame:
    artifact = load_artifact(model_path)
    predictions = predict_frame(load_dataset(input_path), artifact)
    destination = ensure_parent(output_path)
    predictions.to_csv(destination, index=False)
    return predictions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--input", help="Input CSV; defaults to configured prediction_input")
    parser.add_argument("--model", help="Joblib artifact; defaults to configured model_output")
    parser.add_argument("--output", help="Output CSV; defaults to configured predictions_output")
    args = parser.parse_args()

    config = load_config(args.config)
    input_path = Path(args.input) if args.input else config["paths"]["prediction_input"]
    model_path = Path(args.model) if args.model else config["paths"]["model_output"]
    output_path = Path(args.output) if args.output else config["paths"]["predictions_output"]
    predictions = predict_csv(input_path, model_path, output_path)
    print(f"Loaded model artifact: {model_path}")
    print(f"Wrote {len(predictions)} predictions to {output_path}")


if __name__ == "__main__":
    main()
