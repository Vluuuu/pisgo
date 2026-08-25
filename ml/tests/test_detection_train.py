from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from pisgo_ml.detection_train import (
    DetectionTrainingError,
    _dataset_fingerprint,
    count_detection_errors,
    evaluate_detector,
    extract_ultralytics_metrics,
    load_detector_config,
    median_latency_ms,
    train_detector,
    validate_built_dataset,
)


def _config(tmp_path: Path) -> Path:
    root = tmp_path / "dataset"
    rows = []
    for split in ("train", "val", "test"):
        for status in ("positive", "negative"):
            image_id = f"{split}-{status}"
            image_file = f"{image_id}.jpg"
            (root / "images" / split).mkdir(parents=True, exist_ok=True)
            (root / "labels" / split).mkdir(parents=True, exist_ok=True)
            (root / "images" / split / image_file).write_bytes(b"image")
            (root / "labels" / split / f"{image_id}.txt").write_text(
                "0 0.5 0.5 0.4 0.4\n" if status == "positive" else "",
                encoding="utf-8",
            )
            rows.append(
                {
                    "image_id": image_id,
                    "image_file": image_file,
                    "final_status": status,
                    "group_id": image_id,
                    "split": split,
                }
            )
    manifest = root / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (root / "data.yaml").write_text(
        "path: .\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: banana_bunch\n",
        encoding="utf-8",
    )
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps(
            {
                "status": "DATASET_READY_FOR_REVIEW",
                "stage": "annotation_audit",
                "blockers": [],
                "counts": {"dataset_sha256": _dataset_fingerprint(root)},
            }
        ),
        encoding="utf-8",
    )
    config = {
        "project": {"name": "test", "model_version": "test-yolo", "random_seed": 42},
        "paths": {
            "dataset_audit": str(audit),
            "data_yaml": str(root / "data.yaml"),
            "dataset_manifest": str(manifest),
            "run_dir": str(tmp_path / "runs" / "test-yolo"),
            "checkpoint": str(tmp_path / "models" / "test.pt"),
            "metrics_output": str(tmp_path / "metrics.json"),
            "manual_inspection": str(tmp_path / "manual.csv"),
        },
        "model": {
            "pretrained_weights": "yolo11n.pt",
            "image_size": 640,
            "batch_size": 2,
            "epochs": 3,
            "patience": 1,
            "device": "cpu",
            "workers": 0,
        },
        "evaluation": {
            "confidence_threshold": 0.25,
            "nms_iou_threshold": 0.7,
            "matching_iou_threshold": 0.5,
            "latency_warmup_images": 1,
        },
        "provenance": {
            "package_url": "https://github.com/ultralytics/ultralytics",
            "package_version": "8.4.127",
            "package_license": "AGPL-3.0",
            "weights_url": "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11n.pt",
            "weights_release": "v8.4.0",
            "weights_license": "AGPL-3.0",
            "checked_at": "2026-08-24",
        },
    }
    path = tmp_path / "detector.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_training_requires_ready_audit(tmp_path):
    path = _config(tmp_path)
    config = load_detector_config(path)
    config["paths"]["dataset_audit"].write_text(
        json.dumps({"status": "YOLO_DATASET_BLOCKED", "stage": "annotation_audit", "blockers": ["missing labels"]}),
        encoding="utf-8",
    )

    with pytest.raises(DetectionTrainingError, match="missing labels"):
        validate_built_dataset(config)


def test_built_dataset_accepts_emergency_ready_audit(tmp_path):
    path = _config(tmp_path)
    config = load_detector_config(path)
    audit = config["paths"]["dataset_audit"]
    payload = json.loads(audit.read_text(encoding="utf-8"))
    payload.update(
        {
            "status": "EMERGENCY_YOLO_DATASET_READY",
            "stage": "emergency_annotation_audit",
        }
    )
    audit.write_text(json.dumps(payload), encoding="utf-8")

    assert validate_built_dataset(config)["fingerprint"] == _dataset_fingerprint(
        tmp_path / "dataset"
    )


def test_built_dataset_rejects_invalid_positive_geometry(tmp_path):
    path = _config(tmp_path)
    config = load_detector_config(path)
    label = tmp_path / "dataset/labels/train/train-positive.txt"
    label.write_text("0 0.5 0.95 0.4 0.2\n", encoding="utf-8")
    audit = config["paths"]["dataset_audit"]
    payload = json.loads(audit.read_text(encoding="utf-8"))
    payload["counts"]["dataset_sha256"] = _dataset_fingerprint(tmp_path / "dataset")
    audit.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DetectionTrainingError, match="Invalid built class-0 label"):
        validate_built_dataset(config)


def test_built_dataset_rejects_label_status_mismatch(tmp_path):
    path = _config(tmp_path)
    config = load_detector_config(path)
    negative = tmp_path / "dataset" / "labels" / "train" / "train-negative.txt"
    negative.write_text("0 0.5 0.5 0.4 0.4\n", encoding="utf-8")
    audit = config["paths"]["dataset_audit"]
    payload = json.loads(audit.read_text(encoding="utf-8"))
    payload["counts"]["dataset_sha256"] = _dataset_fingerprint(tmp_path / "dataset")
    audit.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DetectionTrainingError, match="label/status mismatch"):
        validate_built_dataset(config)


def test_built_dataset_rejects_group_leakage(tmp_path):
    path = _config(tmp_path)
    config = load_detector_config(path)
    manifest = config["paths"]["dataset_manifest"]
    rows = list(csv.DictReader(manifest.open(encoding="utf-8")))
    rows[0]["group_id"] = rows[-1]["group_id"]
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    audit = config["paths"]["dataset_audit"]
    payload = json.loads(audit.read_text(encoding="utf-8"))
    payload["counts"]["dataset_sha256"] = _dataset_fingerprint(tmp_path / "dataset")
    audit.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DetectionTrainingError, match="group leakage"):
        validate_built_dataset(config)


def test_built_dataset_rejects_changes_after_audit(tmp_path):
    path = _config(tmp_path)
    (tmp_path / "dataset" / "images" / "train" / "train-positive.jpg").write_bytes(
        b"changed"
    )

    with pytest.raises(DetectionTrainingError, match="audit fingerprint"):
        validate_built_dataset(load_detector_config(path))


def test_training_saves_resolved_config_and_best_checkpoint(tmp_path):
    path = _config(tmp_path)
    created = []
    canonical_image = tmp_path / "dataset/images/train/train-positive.jpg"
    canonical_bytes = canonical_image.read_bytes()
    runtime_roots = []

    class FakeModel:
        def __init__(self, weights):
            created.append(weights)
            self.trainer = None

        def train(self, **kwargs):
            data = yaml.safe_load(Path(kwargs["data"]).read_text(encoding="utf-8"))
            runtime_root = Path(data["path"])
            runtime_roots.append(runtime_root)
            (runtime_root / "images/train/train-positive.jpg").write_bytes(b"repaired")
            (runtime_root / "labels/train.cache").write_bytes(b"cache")
            save_dir = Path(kwargs["project"]) / kwargs["name"]
            best = save_dir / "weights" / "best.pt"
            best.parent.mkdir(parents=True)
            best.write_bytes(b"checkpoint")
            self.trainer = SimpleNamespace(save_dir=save_dir)

    result = train_detector(path, model_factory=FakeModel)

    assert created == ["yolo11n.pt"]
    assert canonical_image.read_bytes() == canonical_bytes
    assert runtime_roots and not runtime_roots[0].exists()
    assert Path(result["checkpoint"]).read_bytes() == b"checkpoint"
    resolved = tmp_path / "runs" / "test-yolo" / "resolved_config.json"
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    assert payload["project"]["random_seed"] == 42
    assert payload["model"]["patience"] == 1
    assert payload["provenance"]["weights_license"] == "AGPL-3.0"
    assert payload["dataset"]["fingerprint_sha256"] == _dataset_fingerprint(
        tmp_path / "dataset"
    )


def test_evaluation_uses_and_removes_isolated_dataset_copy(tmp_path):
    path = _config(tmp_path)
    config = load_detector_config(path)
    config["paths"]["checkpoint"].parent.mkdir(parents=True)
    config["paths"]["checkpoint"].write_bytes(b"checkpoint")
    config["paths"]["run_dir"].mkdir(parents=True)
    dataset = validate_built_dataset(config)
    (config["paths"]["run_dir"] / "resolved_config.json").write_text(
        json.dumps(
            {
                "evaluation": config["evaluation"],
                "dataset": {"fingerprint_sha256": dataset["fingerprint"]},
            }
        ),
        encoding="utf-8",
    )
    canonical_image = tmp_path / "dataset/images/test/test-positive.jpg"
    canonical_bytes = canonical_image.read_bytes()
    runtime_roots = []

    class FakeBoxes:
        xyxyn = []
        conf = []

    class FakeModel:
        def val(self, **kwargs):
            data = yaml.safe_load(Path(kwargs["data"]).read_text(encoding="utf-8"))
            runtime_root = Path(data["path"])
            runtime_roots.append(runtime_root)
            (runtime_root / "images/test/test-positive.jpg").write_bytes(b"repaired")
            (runtime_root / "labels/test.cache").write_bytes(b"cache")
            return SimpleNamespace(box=SimpleNamespace(mp=0.8, mr=0.7, map50=0.75, map=0.5))

        def predict(self, **kwargs):
            assert Path(kwargs["source"]).is_relative_to(runtime_roots[0])
            return [SimpleNamespace(boxes=FakeBoxes())]

    result = evaluate_detector(path, model_factory=lambda weights: FakeModel())

    assert canonical_image.read_bytes() == canonical_bytes
    assert runtime_roots and not runtime_roots[0].exists()
    assert result["test_images"] == 2


def test_evaluation_rejects_changed_threshold(tmp_path):
    path = _config(tmp_path)
    config = load_detector_config(path)
    config["paths"]["checkpoint"].parent.mkdir(parents=True)
    config["paths"]["checkpoint"].write_bytes(b"checkpoint")
    config["paths"]["run_dir"].mkdir(parents=True)
    dataset = validate_built_dataset(config)
    frozen_evaluation = {**config["evaluation"], "confidence_threshold": 0.5}
    (config["paths"]["run_dir"] / "resolved_config.json").write_text(
        json.dumps(
            {
                "evaluation": frozen_evaluation,
                "dataset": {"fingerprint_sha256": dataset["fingerprint"]},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DetectionTrainingError, match="settings changed"):
        evaluate_detector(path, model_factory=lambda weights: object())


def test_detection_error_accounting_matches_boxes_once():
    truth = [(0.1, 0.1, 0.5, 0.5), (0.6, 0.6, 0.9, 0.9)]
    predictions = [(0.1, 0.1, 0.5, 0.5), (0.0, 0.0, 0.05, 0.05)]

    assert count_detection_errors(truth, predictions, iou_threshold=0.5) == (1, 1)
    assert count_detection_errors([], predictions, iou_threshold=0.5) == (2, 0)


def test_detection_error_accounting_finds_maximum_matching():
    truth = [(0.0, 0.0, 0.6, 1.0), (0.4, 0.0, 1.0, 1.0)]
    predictions = [(0.1, 0.0, 0.7, 1.0), (0.0, 0.0, 0.6, 1.0)]

    assert count_detection_errors(truth, predictions, iou_threshold=0.3) == (0, 0)
    assert count_detection_errors(truth, list(reversed(predictions)), iou_threshold=0.3) == (0, 0)


def test_metric_extraction_and_latency_summary():
    metrics = SimpleNamespace(box=SimpleNamespace(mp=0.8, mr=0.7, map50=0.75, map=0.5))
    assert extract_ultralytics_metrics(metrics) == {
        "precision": 0.8,
        "recall": 0.7,
        "map50": 0.75,
        "map50_95": 0.5,
    }
    calls = []
    value = median_latency_ms(lambda source: calls.append(source), [Path("a"), Path("b")], warmup=1)
    assert value is not None and value >= 0
    assert calls == [Path("a"), Path("a"), Path("b")]
