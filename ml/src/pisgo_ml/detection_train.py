"""Train and evaluate one fail-closed banana-bunch YOLO baseline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

from .detection_dataset import DetectionDatasetError, parse_yolo_label
from .utils import ensure_parent, write_json

READY_AUDITS = {
    ("DATASET_READY_FOR_REVIEW", "annotation_audit"),
    ("EMERGENCY_YOLO_DATASET_READY", "emergency_annotation_audit"),
}


class DetectionTrainingError(ValueError):
    """Raised when the audited detector dataset or run contract is incomplete."""


def load_detector_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise DetectionTrainingError(f"Detector configuration not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    required = {"project", "paths", "model", "evaluation", "provenance"}
    if missing := sorted(required - set(config)):
        raise DetectionTrainingError(
            f"Detector configuration is missing sections: {', '.join(missing)}"
        )
    project_root = path.parent.parent
    config["_config_path"] = path
    config["_project_root"] = project_root
    for key, value in config["paths"].items():
        candidate = Path(value).expanduser()
        config["paths"][key] = candidate if candidate.is_absolute() else project_root / candidate
    model = config["model"]
    if str(model.get("pretrained_weights")) != "yolo11n.pt":
        raise DetectionTrainingError("The approved baseline is fixed to yolo11n.pt")
    if str(model.get("device")) != "cpu":
        raise DetectionTrainingError("The approved baseline and latency contract require CPU")
    evidence = config["provenance"]
    if any(
        not str(evidence.get(key, "")).strip()
        for key in (
            "package_url",
            "package_version",
            "package_license",
            "weights_url",
            "weights_release",
            "weights_license",
            "checked_at",
        )
    ):
        raise DetectionTrainingError("Detector package and pretrained-weight license evidence is incomplete")
    if evidence["package_license"] != "AGPL-3.0" or evidence["weights_license"] != "AGPL-3.0":
        raise DetectionTrainingError("The approved detector baseline requires explicit AGPL-3.0 evidence")
    evidence["checked_at"] = str(evidence["checked_at"])
    return config


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dataset_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(_file_sha256(path).encode("ascii"))
    return digest.hexdigest()


def validate_built_dataset(config: dict[str, Any]) -> dict[str, Any]:
    paths = config["paths"]
    audit_path: Path = paths["dataset_audit"]
    data_yaml: Path = paths["data_yaml"]
    manifest_path: Path = paths["dataset_manifest"]
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DetectionTrainingError(f"Detection audit not found: {audit_path}") from error
    except json.JSONDecodeError as error:
        raise DetectionTrainingError(f"Detection audit is malformed: {error}") from error
    if (
        (audit.get("status"), audit.get("stage")) not in READY_AUDITS
        or audit.get("blockers")
    ):
        blockers = audit.get("blockers") or [f"status={audit.get('status')}"]
        raise DetectionTrainingError("Detection dataset is not training-ready: " + "; ".join(blockers))
    expected_fingerprint = str(audit.get("counts", {}).get("dataset_sha256", ""))
    if not expected_fingerprint:
        raise DetectionTrainingError("Detection audit lacks a built-dataset fingerprint")
    if not data_yaml.is_file() or not manifest_path.is_file():
        raise DetectionTrainingError("Built detector data.yaml and manifest.csv are required")

    rows = _read_csv(manifest_path)
    required = {"image_id", "image_file", "final_status", "group_id", "split"}
    if not rows or required - set(rows[0]):
        raise DetectionTrainingError("Built detector manifest is empty or incomplete")
    ids = [row["image_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise DetectionTrainingError("Built detector manifest contains duplicate image IDs")
    root = data_yaml.parent
    for row in rows:
        split = row["split"]
        if split not in {"train", "val", "test"}:
            raise DetectionTrainingError(f"Invalid detector split: {split}")
        if row["final_status"] not in {"positive", "negative"}:
            raise DetectionTrainingError(f"Invalid detector final_status: {row['image_id']}")
        if not (root / "images" / split / row["image_file"]).is_file():
            raise DetectionTrainingError(f"Built image is missing: {row['image_id']}")
        label = root / "labels" / split / f"{Path(row['image_file']).stem}.txt"
        if not label.is_file():
            raise DetectionTrainingError(f"Built label is missing: {row['image_id']}")
        try:
            boxes = parse_yolo_label(label.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, DetectionDatasetError) as error:
            raise DetectionTrainingError(
                f"Invalid built class-0 label {row['image_id']}: {error}"
            ) from error
        if bool(boxes) != (row["final_status"] == "positive"):
            raise DetectionTrainingError(
                f"Built label/status mismatch: {row['image_id']}"
            )

    group_splits: dict[str, set[str]] = {}
    for row in rows:
        group_splits.setdefault(row["group_id"], set()).add(row["split"])
    if any(len(splits) != 1 for splits in group_splits.values()):
        raise DetectionTrainingError("Detector group leakage remains across splits")
    split_counts = {
        split: {
            "images": sum(row["split"] == split for row in rows),
            "positive": sum(
                row["split"] == split and row["final_status"] == "positive"
                for row in rows
            ),
            "negative": sum(
                row["split"] == split and row["final_status"] == "negative"
                for row in rows
            ),
            "groups": len(
                {row["group_id"] for row in rows if row["split"] == split}
            ),
        }
        for split in ("train", "val", "test")
    }
    for split, counts in split_counts.items():
        if counts["images"] == 0 or counts["positive"] == 0:
            raise DetectionTrainingError(
                f"Detector split {split} requires images and at least one positive"
            )
    if split_counts["test"]["negative"] == 0:
        raise DetectionTrainingError("Detector test split requires verified negatives")
    for split in ("train", "val", "test"):
        expected_images = {row["image_file"] for row in rows if row["split"] == split}
        actual_images = {
            path.name for path in (root / "images" / split).iterdir() if path.is_file()
        }
        expected_labels = {f"{Path(name).stem}.txt" for name in expected_images}
        actual_labels = {
            path.name for path in (root / "labels" / split).iterdir() if path.is_file()
        }
        if actual_images != expected_images or actual_labels != expected_labels:
            raise DetectionTrainingError(f"Detector {split} inventory does not match manifest")
    fingerprint = _dataset_fingerprint(root)
    if fingerprint != expected_fingerprint:
        raise DetectionTrainingError("Built detector dataset does not match its audit fingerprint")
    return {
        "root": root,
        "data_yaml": data_yaml,
        "manifest_path": manifest_path,
        "rows": rows,
        "counts": split_counts,
        "fingerprint": fingerprint,
    }


def _resolved_data_yaml(dataset: dict[str, Any], destination: Path) -> Path:
    with dataset["data_yaml"].open("r", encoding="utf-8") as handle:
        source = yaml.safe_load(handle) or {}
    payload = {
        "path": dataset["root"].resolve().as_posix(),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": source.get("names", {0: "banana_bunch"}),
    }
    ensure_parent(destination).write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )
    return destination


def _runtime_dataset_copy(dataset: dict[str, Any], destination: Path) -> dict[str, Any]:
    if destination.exists():
        raise DetectionTrainingError(
            f"Detector runtime dataset already exists; refusing to overwrite: {destination}"
        )
    shutil.copytree(dataset["root"], destination, copy_function=shutil.copy2)
    return {**dataset, "root": destination, "data_yaml": destination / "data.yaml"}


def _assert_frozen_dataset(dataset: dict[str, Any]) -> None:
    if _dataset_fingerprint(dataset["root"]) != dataset["fingerprint"]:
        raise DetectionTrainingError("Built detector dataset changed during model execution")


def _ultralytics_yolo(expected_version: str) -> Callable[[str], Any]:
    try:
        import ultralytics
        from ultralytics import YOLO
    except ImportError as error:
        raise DetectionTrainingError(
            "Ultralytics is not installed; install the pinned ML dependencies"
        ) from error
    if ultralytics.__version__ != expected_version:
        raise DetectionTrainingError(
            "Installed Ultralytics version does not match provenance: "
            f"expected {expected_version}, found {ultralytics.__version__}"
        )
    return YOLO


def train_detector(
    config_path: str | Path,
    *,
    model_factory: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    config = load_detector_config(config_path)
    dataset = validate_built_dataset(config)
    paths = config["paths"]
    run_dir: Path = paths["run_dir"]
    checkpoint: Path = paths["checkpoint"]
    if run_dir.exists() or checkpoint.exists():
        raise DetectionTrainingError(
            f"Detector run already exists; refusing to overwrite: {run_dir}"
        )
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    runtime_root = run_dir.parent / f".{run_dir.name}-dataset"
    runtime_dataset = _runtime_dataset_copy(dataset, runtime_root)
    resolved_data = _resolved_data_yaml(
        runtime_dataset, run_dir / "resolved_data.yaml"
    )
    resolved_config = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project": config["project"],
        "model": config["model"],
        "evaluation": config["evaluation"],
        "provenance": config["provenance"],
        "dataset": {
            "counts": dataset["counts"],
            "data_yaml": str(resolved_data),
            "fingerprint_sha256": dataset["fingerprint"],
        },
    }
    write_json(resolved_config, run_dir / "resolved_config.json")

    started = time.perf_counter()
    try:
        factory = model_factory or _ultralytics_yolo(
            config["provenance"]["package_version"]
        )
        model = factory(str(config["model"]["pretrained_weights"]))
        model.train(
            data=str(resolved_data),
            project=str(run_dir.parent),
            name=run_dir.name,
            exist_ok=True,
            epochs=int(config["model"]["epochs"]),
            patience=int(config["model"]["patience"]),
            imgsz=int(config["model"]["image_size"]),
            batch=int(config["model"]["batch_size"]),
            device=str(config["model"]["device"]),
            workers=int(config["model"]["workers"]),
            seed=int(config["project"]["random_seed"]),
            deterministic=True,
            cache=False,
            plots=True,
            verbose=True,
        )
        _assert_frozen_dataset(dataset)
        save_dir = Path(model.trainer.save_dir)
        best = save_dir / "weights" / "best.pt"
        if not best.is_file():
            raise DetectionTrainingError(f"Ultralytics did not produce best.pt: {best}")
        ensure_parent(checkpoint)
        shutil.copy2(best, checkpoint)
        result = {
            "status": "YOLO_BASELINE_TRAINED_PENDING_TEST_EVALUATION",
            "model_version": config["project"]["model_version"],
            "checkpoint": str(checkpoint),
            "checkpoint_bytes": checkpoint.stat().st_size,
            "checkpoint_sha256": _file_sha256(checkpoint),
            "run_dir": str(save_dir),
            "training_seconds": round(time.perf_counter() - started, 3),
            "dataset_counts": dataset["counts"],
        }
        write_json(result, run_dir / "training_summary.json")
        return result
    except Exception:
        if not checkpoint.exists():
            shutil.rmtree(run_dir, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)


def _box_iou(left: Iterable[float], right: Iterable[float]) -> float:
    lx1, ly1, lx2, ly2 = (float(value) for value in left)
    rx1, ry1, rx2, ry2 = (float(value) for value in right)
    intersection = max(0.0, min(lx2, rx2) - max(lx1, rx1)) * max(
        0.0, min(ly2, ry2) - max(ly1, ry1)
    )
    union = (lx2 - lx1) * (ly2 - ly1) + (rx2 - rx1) * (ry2 - ry1) - intersection
    return intersection / union if union > 0 else 0.0


def _yolo_truth(path: Path) -> list[tuple[float, float, float, float]]:
    try:
        boxes = parse_yolo_label(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, DetectionDatasetError) as error:
        raise DetectionTrainingError(f"Invalid class-0 test label {path}: {error}") from error
    return [
        (x - width / 2, y - height / 2, x + width / 2, y + height / 2)
        for x, y, width, height in boxes
    ]


def count_detection_errors(
    truth: list[Iterable[float]],
    predictions: list[Iterable[float]],
    *,
    iou_threshold: float,
) -> tuple[int, int]:
    edges = [
        [
            index
            for index, target in enumerate(truth)
            if _box_iou(prediction, target) >= iou_threshold
        ]
        for prediction in predictions
    ]
    matched_truth: dict[int, int] = {}

    def match(prediction_index: int, visited: set[int]) -> bool:
        for truth_index in edges[prediction_index]:
            if truth_index in visited:
                continue
            visited.add(truth_index)
            previous = matched_truth.get(truth_index)
            if previous is None or match(previous, visited):
                matched_truth[truth_index] = prediction_index
                return True
        return False

    matched = sum(match(index, set()) for index in range(len(predictions)))
    return len(predictions) - matched, len(truth) - matched


def extract_ultralytics_metrics(metrics: Any) -> dict[str, float]:
    try:
        return {
            "precision": float(metrics.box.mp),
            "recall": float(metrics.box.mr),
            "map50": float(metrics.box.map50),
            "map50_95": float(metrics.box.map),
        }
    except (AttributeError, TypeError, ValueError) as error:
        raise DetectionTrainingError("Ultralytics test metrics are incomplete") from error


def median_latency_ms(
    infer: Callable[[Path], Any], sources: list[Path], *, warmup: int
) -> float | None:
    if not sources:
        return None
    for source in sources[:warmup]:
        infer(source)
    durations = []
    for source in sources:
        started = time.perf_counter()
        infer(source)
        durations.append((time.perf_counter() - started) * 1000)
    return round(statistics.median(durations), 3)


def _prediction_boxes(result: Any) -> list[list[float]]:
    boxes = getattr(result, "boxes", None)
    coordinates = getattr(boxes, "xyxyn", None)
    if coordinates is None:
        return []
    if hasattr(coordinates, "cpu"):
        coordinates = coordinates.cpu()
    if hasattr(coordinates, "tolist"):
        coordinates = coordinates.tolist()
    return [[float(value) for value in row] for row in coordinates]


def _prediction_scores(result: Any) -> list[float]:
    confidence = getattr(getattr(result, "boxes", None), "conf", None)
    if confidence is None:
        return []
    if hasattr(confidence, "cpu"):
        confidence = confidence.cpu()
    if hasattr(confidence, "tolist"):
        confidence = confidence.tolist()
    return [float(value) for value in confidence]


def evaluate_detector(
    config_path: str | Path,
    *,
    model_factory: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    config = load_detector_config(config_path)
    dataset = validate_built_dataset(config)
    paths = config["paths"]
    checkpoint: Path = paths["checkpoint"]
    if not checkpoint.is_file():
        raise DetectionTrainingError(f"Detector checkpoint not found: {checkpoint}")
    metrics_output: Path = paths["metrics_output"]
    if metrics_output.exists():
        raise DetectionTrainingError(
            f"Held-out metrics already exist; refusing repeat evaluation: {metrics_output}"
        )
    resolved_config_path: Path = paths["run_dir"] / "resolved_config.json"
    try:
        frozen = json.loads(resolved_config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DetectionTrainingError(
            f"Frozen training configuration not found: {resolved_config_path}"
        ) from error
    except json.JSONDecodeError as error:
        raise DetectionTrainingError(f"Frozen training configuration is malformed: {error}") from error
    if frozen.get("evaluation") != config["evaluation"]:
        raise DetectionTrainingError("Evaluation settings changed after training")
    if frozen.get("dataset", {}).get("fingerprint_sha256") != dataset["fingerprint"]:
        raise DetectionTrainingError("Built detector dataset changed after training")
    runtime_root = checkpoint.parent / f".{checkpoint.stem}-evaluation-dataset"
    runtime_dataset = _runtime_dataset_copy(dataset, runtime_root)
    runtime_data = runtime_root / "resolved_data.yaml"
    try:
        factory = model_factory or _ultralytics_yolo(
            config["provenance"]["package_version"]
        )
        model = factory(str(checkpoint))
        threshold = float(config["evaluation"]["confidence_threshold"])
        image_size = int(config["model"]["image_size"])
        device = str(config["model"]["device"])
        validation = model.val(
            data=str(_resolved_data_yaml(runtime_dataset, runtime_data)),
            split="test",
            conf=threshold,
            iou=float(config["evaluation"]["nms_iou_threshold"]),
            imgsz=image_size,
            device=device,
            plots=True,
            verbose=True,
        )
        aggregate = extract_ultralytics_metrics(validation)

        test_rows = [row for row in dataset["rows"] if row["split"] == "test"]
        false_positive_detections = 0
        false_positive_negative_detections = 0
        negative_images_with_false_positive = 0
        false_negative_boxes = 0
        positive_images_with_false_negative = 0
        predictions_by_id: dict[str, dict[str, Any]] = {}
        sources: list[Path] = []

        def infer(source: Path) -> Any:
            return model.predict(
                source=str(source),
                conf=threshold,
                iou=float(config["evaluation"]["nms_iou_threshold"]),
                imgsz=image_size,
                device=device,
                verbose=False,
            )[0]

        for row in test_rows:
            source = runtime_dataset["root"] / "images" / "test" / row["image_file"]
            label = runtime_dataset["root"] / "labels" / "test" / f"{Path(row['image_file']).stem}.txt"
            result = infer(source)
            predicted = _prediction_boxes(result)
            truth = _yolo_truth(label)
            false_positives, false_negatives = count_detection_errors(
                truth,
                predicted,
                iou_threshold=float(config["evaluation"]["matching_iou_threshold"]),
            )
            false_positive_detections += false_positives
            if row["final_status"] == "negative":
                false_positive_negative_detections += false_positives
                negative_images_with_false_positive += bool(false_positives)
            else:
                false_negative_boxes += false_negatives
                positive_images_with_false_negative += bool(false_negatives)
            predictions_by_id[row["image_id"]] = {
                "detection_count": len(predicted),
                "max_score": max(_prediction_scores(result), default=0.0),
            }
            sources.append(source)

        latency = median_latency_ms(
            infer,
            sources,
            warmup=int(config["evaluation"]["latency_warmup_images"]),
        )
        _assert_frozen_dataset(dataset)
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)
    result = {
        "status": "YOLO_BASELINE_TRAINED",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": config["project"]["model_version"],
        "checkpoint": str(checkpoint),
        "checkpoint_bytes": checkpoint.stat().st_size,
        "checkpoint_sha256": _file_sha256(checkpoint),
        "dataset_fingerprint_sha256": dataset["fingerprint"],
        "random_seed": int(config["project"]["random_seed"]),
        "confidence_threshold": threshold,
        "matching_iou_threshold": float(config["evaluation"]["matching_iou_threshold"]),
        "test_images": len(test_rows),
        "positive_test_images": sum(row["final_status"] == "positive" for row in test_rows),
        "negative_test_images": sum(row["final_status"] == "negative" for row in test_rows),
        **aggregate,
        "false_positive_detections": false_positive_detections,
        "false_positive_detections_on_verified_negatives": false_positive_negative_detections,
        "negative_images_with_false_positive": negative_images_with_false_positive,
        "false_negative_boxes": false_negative_boxes,
        "positive_images_with_false_negative": positive_images_with_false_negative,
        "median_cpu_inference_milliseconds": latency,
        "field_validation_claimed": False,
    }
    write_json(result, paths["metrics_output"])
    _write_manual_inspection(config, dataset["rows"], predictions_by_id)
    return result


def _write_manual_inspection(
    config: dict[str, Any],
    rows: list[dict[str, str]],
    predictions: dict[str, dict[str, Any]],
) -> None:
    """Write an unclassified review queue; humans assign visual categories."""
    selected = []
    for status in ("positive", "negative"):
        candidates = [
            row
            for row in rows
            if row["image_id"] in predictions and row["final_status"] == status
        ]
        for row in candidates[:5]:
            selected.append(
                {
                    "category": "",
                    "image_id": row["image_id"],
                    "image_file": row["image_file"],
                    "final_status": status,
                    **predictions[row["image_id"]],
                    "human_observation": "",
                }
            )
    destination: Path = config["paths"]["manual_inspection"]
    ensure_parent(destination)
    fields = [
        "category",
        "image_id",
        "image_file",
        "final_status",
        "detection_count",
        "max_score",
        "human_observation",
    ]
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("train", "evaluate"))
    parser.add_argument("--config", default="configs/detection_baseline.yaml")
    args = parser.parse_args()
    action = train_detector if args.command == "train" else evaluate_detector
    print(json.dumps(action(args.config), indent=2))


if __name__ == "__main__":
    main()
