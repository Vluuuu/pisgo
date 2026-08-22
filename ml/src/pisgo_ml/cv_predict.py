"""Run raw Cavendish maturity inference from a persisted image artifact."""

from __future__ import annotations

import argparse
import json
import time
import zipfile
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from .config import load_config
from .utils import write_json


class CVArtifactError(ValueError):
    """Raised when a CV artifact is unsupported or incomplete."""


def load_cv_artifact(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(
            f"CV model artifact not found: {source}. Run cv_train before inference."
        )
    artifact = joblib.load(source)
    if not isinstance(artifact, dict) or artifact.get("artifact_format") != "pisgo_ml.cv.joblib":
        raise CVArtifactError(f"Unsupported CV artifact: {source}")
    required = {"model_version", "labels", "feature_extractor", "classifier"}
    missing = sorted(required - set(artifact))
    if missing:
        raise CVArtifactError(f"CV artifact is missing fields: {', '.join(missing)}")
    return artifact


def predict_image_source(
    source: Any,
    artifact: dict[str, Any],
    input_reference: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    extractor = artifact["feature_extractor"]
    classifier = artifact["classifier"]
    features = extractor.extract(source).reshape(1, -1)
    probabilities = classifier.predict_proba(features)[0]
    classes = [str(value) for value in classifier.classes_]
    probability_map = {label: 0.0 for label in artifact["labels"]}
    probability_map.update(
        {label: float(probability) for label, probability in zip(classes, probabilities)}
    )
    ordered_probabilities = {
        label: round(probability_map[label], 8) for label in artifact["labels"]
    }
    predicted_class = max(ordered_probabilities, key=ordered_probabilities.get)
    return {
        "artifact_format": artifact["artifact_format"],
        "model_version": artifact["model_version"],
        "task": artifact.get("task", "cavendish_maturity_image_classification"),
        "variety": artifact.get("variety", "Cavendish"),
        "input_reference": input_reference,
        "predicted_class": predicted_class,
        "confidence": ordered_probabilities[predicted_class],
        "class_probabilities": ordered_probabilities,
        "preprocessing": artifact.get("preprocessing"),
        "inference_milliseconds": round((time.perf_counter() - started) * 1000, 3),
    }


def predict_image_file(image_path: str | Path, artifact: dict[str, Any]) -> dict[str, Any]:
    source = Path(image_path)
    if not source.is_file():
        raise FileNotFoundError(f"Input image not found: {source}")
    return predict_image_source(source, artifact, str(source))


def predict_archive_member(
    archive_path: str | Path,
    member: str,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    source = Path(archive_path)
    if not source.is_file():
        raise FileNotFoundError(f"Image dataset archive not found: {source}")
    with zipfile.ZipFile(source) as archive:
        try:
            image_bytes = archive.read(member)
        except KeyError as error:
            raise FileNotFoundError(f"Archive member not found: {member}") from error
    return predict_image_source(image_bytes, artifact, f"{source}!/{member}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/cv_baseline.yaml")
    parser.add_argument("--model")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--image", help="Filesystem image path")
    input_group.add_argument("--member", help="Image member path inside dataset ZIP")
    parser.add_argument("--archive", help="ZIP path when --member is used")
    parser.add_argument("--output", help="Optional raw JSON output path")
    args = parser.parse_args()

    config = load_config(args.config)
    model_path = Path(args.model) if args.model else config["paths"]["model_output"]
    artifact = load_cv_artifact(model_path)
    if args.image:
        result = predict_image_file(args.image, artifact)
    else:
        archive_path = Path(args.archive) if args.archive else config["paths"]["dataset_zip"]
        result = predict_archive_member(archive_path, args.member, artifact)

    output_path = Path(args.output) if args.output else config["paths"]["prediction_output"]
    write_json(result, output_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
