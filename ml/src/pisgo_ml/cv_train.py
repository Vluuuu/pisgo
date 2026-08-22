"""Train a leakage-safe Cavendish image maturity baseline directly from ZIP."""

from __future__ import annotations

import argparse
import platform
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from PIL import __version__ as pillow_version
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .config import load_config
from .cv_data import (
    archive_fingerprint,
    assign_grouped_splits,
    build_manifest,
    open_archive_member,
)
from .cv_evaluate import classification_report_metrics
from .cv_features import BananaImageFeatureExtractor
from .utils import ensure_parent, write_json


def _feature_extractor(config: dict[str, Any]) -> BananaImageFeatureExtractor:
    features = config["features"]
    return BananaImageFeatureExtractor(
        resize_width=int(features["resize_width"]),
        resize_height=int(features["resize_height"]),
        histogram_bins=int(features["histogram_bins"]),
        grid_rows=int(features["grid_rows"]),
        grid_columns=int(features["grid_columns"]),
    )


def extract_manifest_features(
    archive_path: str | Path,
    rows: pd.DataFrame,
    extractor: BananaImageFeatureExtractor,
) -> np.ndarray:
    vectors: list[np.ndarray] = []
    with zipfile.ZipFile(archive_path) as archive:
        for member in rows["archive_member"]:
            with open_archive_member(archive, member) as handle:
                vectors.append(extractor.extract(handle))
    return np.vstack(vectors)


def train_cv_from_config(
    config_path: str | Path,
    archive_path: str | Path | None = None,
    model_path: str | Path | None = None,
    metrics_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.perf_counter()
    config = load_config(config_path)
    source = Path(archive_path) if archive_path else config["paths"]["dataset_zip"]
    destination = Path(model_path) if model_path else config["paths"]["model_output"]
    report_destination = (
        Path(metrics_path) if metrics_path else config["paths"]["metrics_output"]
    )
    manifest_destination = (
        Path(manifest_path) if manifest_path else config["paths"]["manifest_output"]
    )

    labels = [str(label).lower() for label in config["data"]["labels"]]
    manifest = build_manifest(source, config["data"]["variety"], labels)
    manifest = assign_grouped_splits(
        manifest,
        train_ratio=float(config["data"]["train_ratio"]),
        validation_ratio=float(config["data"]["validation_ratio"]),
        test_ratio=float(config["data"]["test_ratio"]),
        random_state=int(config["project"]["random_seed"]),
        train_with_augmented=bool(config["data"].get("train_with_augmented", True)),
    )
    ensure_parent(manifest_destination)
    manifest.to_csv(manifest_destination, index=False)

    included = manifest[manifest["included"]].copy()
    extractor = _feature_extractor(config)
    split_data: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    split_summary: dict[str, Any] = {}
    for split in ("train", "validation", "test"):
        rows = included[included["split"] == split]
        split_data[split] = (
            extract_manifest_features(source, rows, extractor),
            rows["maturity_class"].to_numpy(),
        )
        split_summary[split] = {
            "images": int(len(rows)),
            "specimen_groups": int(rows["group_id"].nunique()),
            "class_images": {
                label: int((rows["maturity_class"] == label).sum()) for label in labels
            },
            "class_groups": {
                label: int(rows.loc[rows["maturity_class"] == label, "group_id"].nunique())
                for label in labels
            },
            "augmented_images": int(rows["is_augmented"].sum()),
        }

    X_train, y_train = split_data["train"]
    baseline = DummyClassifier(strategy="most_frequent")
    baseline.fit(X_train, y_train)
    classifier = Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    max_iter=int(config["model"]["max_iter"]),
                    C=float(config["model"]["c"]),
                    class_weight=config["model"].get("class_weight"),
                    random_state=int(config["project"]["random_seed"]),
                ),
            ),
        ]
    )
    classifier.fit(X_train, y_train)

    metrics: dict[str, Any] = {
        "model_version": config["project"]["model_version"],
        "dataset": {
            "archive": str(source),
            "variety": config["data"]["variety"],
            "all_matching_images": int(len(manifest)),
            "all_specimen_groups": int(manifest["group_id"].nunique()),
            "fingerprint": archive_fingerprint(source, manifest),
        },
        "split": {
            "strategy": "stratified_specimen_group_split",
            "group_key": "variety + maturity_class + specimen_id",
            "random_seed": int(config["project"]["random_seed"]),
            "train_with_augmented": bool(config["data"].get("train_with_augmented", True)),
            "partitions": split_summary,
        },
        "baseline": {},
        "model": {},
    }
    for split in ("validation", "test"):
        X_split, y_split = split_data[split]
        metrics["baseline"][split] = classification_report_metrics(
            y_split, baseline.predict(X_split), labels
        )
        metrics["model"][split] = classification_report_metrics(
            y_split, classifier.predict(X_split), labels
        )

    artifact: dict[str, Any] = {
        "artifact_format": "pisgo_ml.cv.joblib",
        "artifact_version": 1,
        "model_version": config["project"]["model_version"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "task": "cavendish_maturity_image_classification",
        "variety": config["data"]["variety"],
        "labels": labels,
        "feature_extractor": extractor,
        "feature_names": extractor.get_feature_names_out().tolist(),
        "classifier": classifier,
        "baseline": baseline,
        "preprocessing": {
            "image_mode": "RGB",
            "resize": [extractor.resize_width, extractor.resize_height],
            "orientation": "EXIF transpose",
            "features": "RGB/HSV histograms and summaries, spatial grid, edge and pixel ratios",
        },
        "dataset": metrics["dataset"],
        "split": metrics["split"],
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "pillow": pillow_version,
            "joblib": joblib.__version__,
        },
        "metrics": metrics,
    }
    metrics["training_seconds"] = float(time.perf_counter() - started)
    ensure_parent(destination)
    joblib.dump(artifact, destination, compress=3)
    write_json(metrics, report_destination)
    return artifact, metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/cv_baseline.yaml")
    parser.add_argument("--archive", help="Override image dataset ZIP")
    parser.add_argument("--model-output")
    parser.add_argument("--metrics-output")
    parser.add_argument("--manifest-output")
    args = parser.parse_args()

    artifact, metrics = train_cv_from_config(
        args.config,
        args.archive,
        args.model_output,
        args.metrics_output,
        args.manifest_output,
    )
    test_metrics = metrics["model"]["test"]
    print(f"Saved CV artifact for {artifact['variety']}: {args.model_output or load_config(args.config)['paths']['model_output']}")
    print(
        f"Test accuracy={test_metrics['accuracy']:.4f} "
        f"macro_f1={test_metrics['macro']['f1']:.4f}"
    )


if __name__ == "__main__":
    main()
