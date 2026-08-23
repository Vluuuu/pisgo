from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from PIL import Image

from pisgo_ml.detection_dataset import (
    DetectionDatasetError,
    _completed_qa_categories,
    _candidate_set_digest,
    _final_curation_decision,
    _freeze_second_reviews,
    accepted_license,
    assign_detection_splits,
    export_offline_review,
    import_offline_review,
    parse_yolo_label,
    record_curation_decision,
)


def test_license_allowlist_requires_a_complete_prefix():
    prefixes = ["CC0", "CC BY", "CC BY-SA"]

    assert accepted_license("CC0", prefixes)
    assert accepted_license("CC BY-SA 4.0", prefixes)
    assert accepted_license("CC BY 3.0 us", prefixes)
    assert not accepted_license("", prefixes)
    assert not accepted_license("Copyrighted", prefixes)
    assert not accepted_license("CC BY-NC 4.0", prefixes)
    assert not accepted_license("CC BY-SA-NC 4.0", prefixes)


def test_yolo_parser_accepts_positive_and_explicit_empty_negative():
    assert parse_yolo_label("") == []
    assert parse_yolo_label("0 0.5 0.5 0.4 0.2\n") == [(0.5, 0.5, 0.4, 0.2)]


@pytest.mark.parametrize(
    "label",
    [
        "1 0.5 0.5 0.4 0.2",
        "0 0.5 0.5 0.4",
        "0 nan 0.5 0.4 0.2",
        "0 0.1 0.5 0.4 0.2",
        "0 0.5 0.5 0 0.2",
        "0 0.5 0.5 0.4 0.2\n0 0.5 0.5 0.4 0.2",
    ],
)
def test_yolo_parser_rejects_invalid_or_duplicate_boxes(label):
    with pytest.raises(DetectionDatasetError):
        parse_yolo_label(label)


def test_qa_categories_require_matching_review_status(tmp_path):
    path = tmp_path / "human_qa.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["category", "image_id", "reviewer", "reviewed_at"],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "category": "positive",
                    "image_id": "positive",
                    "reviewer": "reviewer",
                    "reviewed_at": "2026-08-23",
                },
                {
                    "category": "negative",
                    "image_id": "positive",
                    "reviewer": "reviewer",
                    "reviewed_at": "2026-08-23",
                },
                {
                    "category": "occluded",
                    "image_id": "positive",
                    "reviewer": "reviewer",
                    "reviewed_at": "2026-08-23",
                },
            ]
        )

    assert _completed_qa_categories(
        path, {"positive": "positive", "negative": "negative"}
    ) == {"positive", "occluded"}


def test_grouped_detection_split_is_deterministic_and_has_positives():
    rows = [
        {
            "group_id": f"positive-{number}",
            "final_status": "positive",
        }
        for number in range(6)
    ] + [
        {
            "group_id": f"negative-{number}",
            "final_status": "negative",
        }
        for number in range(6)
    ]

    first = assign_detection_splits(rows, (0.5, 0.25, 0.25), 42)
    second = assign_detection_splits(rows, (0.5, 0.25, 0.25), 42)

    assert first == second
    assert set(first.values()) == {"train", "val", "test"}
    for split in ("train", "val", "test"):
        assert any(
            row["final_status"] == "positive" and first[row["group_id"]] == split
            for row in rows
        )


def test_grouped_detection_split_requires_three_positive_groups():
    rows = [
        {"group_id": "same-positive", "final_status": "positive"},
        {"group_id": "same-positive", "final_status": "positive"},
        {"group_id": "negative", "final_status": "negative"},
    ]
    with pytest.raises(DetectionDatasetError, match="three positive groups"):
        assign_detection_splits(rows, (0.7, 0.15, 0.15), 42)


def test_second_review_freeze_covers_uncertain_and_ten_percent_per_role():
    rows = [
        {
            "image_id": f"positive-{number}",
            "candidate_role": "positive_candidate",
            "first_decision": "needs_review" if number == 0 else "include",
            "second_required": "",
            "second_reason": "",
        }
        for number in range(21)
    ] + [
        {
            "image_id": f"negative-{number}",
            "candidate_role": "hard_negative_candidate",
            "first_decision": "include",
            "second_required": "",
            "second_reason": "",
        }
        for number in range(11)
    ]

    _freeze_second_reviews(rows, 42)

    assert rows[0]["second_reason"] == "needs_review"
    assert (
        sum(
            row["second_reason"] == "spot_check"
            for row in rows
            if row["candidate_role"] == "positive_candidate"
        )
        == 2
    )
    assert (
        sum(
            row["second_reason"] == "spot_check"
            for row in rows
            if row["candidate_role"] == "hard_negative_candidate"
        )
        == 2
    )


def test_final_curation_decision_never_silently_resolves_disagreement():
    base = {
        "first_decision": "include",
        "second_required": "true",
        "second_reason": "spot_check",
        "second_decision": "",
    }

    assert _final_curation_decision(base) == "needs_review"
    assert _final_curation_decision({**base, "second_decision": "include"}) == "include"
    assert _final_curation_decision({**base, "second_decision": "exclude"}) == "needs_review"
    assert (
        _final_curation_decision(
            {
                **base,
                "first_decision": "needs_review",
                "second_reason": "needs_review",
                "second_decision": "exclude",
            }
        )
        == "exclude"
    )


def test_second_reviewer_must_differ_from_first(tmp_path):
    config, candidates = _offline_fixture(tmp_path)
    receipt = _receipt(
        tmp_path / "receipt.json",
        candidates,
        [
            {
                "candidate_id": candidate["image_id"],
                "curator_decision": "needs_review" if number == 0 else "exclude",
                "reviewed_at": "2026-08-23T10:00:00+00:00",
            }
            for number, candidate in enumerate(candidates)
        ],
    )
    import_offline_review(config, receipt)

    with pytest.raises(DetectionDatasetError, match="must differ"):
        record_curation_decision(
            config,
            image_id=candidates[0]["image_id"],
            stage="second",
            decision="include",
            reviewer="reviewer one",
        )


def _offline_fixture(tmp_path: Path) -> tuple[Path, list[dict[str, str]]]:
    project = tmp_path / "ml"
    images = project / "datasets/raw/banana_bunch_detection/images"
    images.mkdir(parents=True)
    candidates = []
    fields = [
        "image_id", "source_provider", "source_item_id", "source_page_url",
        "original_url", "author", "license", "license_url", "retrieved_at",
        "provenance_status", "search_query", "candidate_role", "local_path",
        "mime_type", "width", "height", "bytes", "sha256", "perceptual_hash",
        "is_augmented", "specimen_id", "group_id", "curator_decision",
    ]
    for number, role in enumerate(("positive_candidate", "hard_negative_candidate")):
        image_id = f"candidate-{number}"
        image_path = images / f"{image_id}.jpg"
        Image.new("RGB", (20, 10), (number * 50, 150, 50)).save(image_path)
        import hashlib
        candidates.append({
            "image_id": image_id, "source_provider": "Wikimedia Commons",
            "source_item_id": f"File:{image_id}.jpg", "source_page_url": f"https://example.test/{image_id}",
            "original_url": f"https://example.test/{image_id}.jpg", "author": "Human",
            "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0",
            "retrieved_at": "2026-08-23T00:00:00+00:00", "provenance_status": "verified",
            "search_query": "banana", "candidate_role": role,
            "local_path": f"datasets/raw/banana_bunch_detection/images/{image_id}.jpg",
            "mime_type": "image/jpeg", "width": "20", "height": "10",
            "bytes": str(image_path.stat().st_size), "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
            "perceptual_hash": f"{number:016x}", "is_augmented": "false",
            "specimen_id": image_id, "group_id": image_id, "curator_decision": "pending",
        })
    manifest = project / "datasets/raw/banana_bunch_detection/candidates.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(candidates)
    config = project / "configs/detection_dataset.yaml"
    config.parent.mkdir()
    config.write_text(
        "project:\n  name: test\n  random_seed: 42\npaths:\n"
        "  candidate_dir: datasets/raw/banana_bunch_detection/images\n"
        "  candidate_manifest: datasets/raw/banana_bunch_detection/candidates.csv\n"
        "  handoff_dir: datasets/processed/handoff\n  annotation_export: datasets/processed/export\n"
        "  dataset_dir: datasets/processed/dataset\n  report_json: datasets/processed/audit.json\n"
        "  report_markdown: datasets/processed/audit.md\nsource:\n  targets:\n    positive_candidate: 2\n"
        "data:\n  near_duplicate_hamming_distance: 3\n",
        encoding="utf-8",
    )
    return config, candidates


def _receipt(path: Path, candidates: list[dict[str, str]], decisions: list[dict[str, str]], reviewer: str = "Reviewer One") -> Path:
    path.write_text(json.dumps({
        "version": 1, "review_id": "review-one", "bundle_digest": _candidate_set_digest(candidates),
        "reviewer": reviewer, "decisions": decisions,
    }), encoding="utf-8")
    return path


def test_offline_export_preserves_candidate_ids(tmp_path):
    config, candidates = _offline_fixture(tmp_path)
    result = export_offline_review(config, "review-one")
    manifest = json.loads((Path(result["path"]) / "review_manifest.json").read_text(encoding="utf-8"))
    assert [row["candidate_id"] for row in manifest["candidates"]] == [row["image_id"] for row in candidates]
    assert all((Path(result["path"]) / row["image_file"]).is_file() for row in manifest["candidates"])


def test_offline_import_valid_receipt_preserves_unreviewed_and_provenance(tmp_path):
    config, candidates = _offline_fixture(tmp_path)
    original_url = candidates[0]["source_page_url"]
    receipt = _receipt(tmp_path / "receipt.json", candidates, [{
        "candidate_id": candidates[0]["image_id"], "curator_decision": "include",
        "reviewed_at": "2026-08-23T10:00:00+00:00",
    }])
    result = import_offline_review(config, receipt)
    rows = list(csv.DictReader((config.parent.parent / "datasets/raw/banana_bunch_detection/curation.csv").open(encoding="utf-8")))
    manifest = list(csv.DictReader((config.parent.parent / "datasets/raw/banana_bunch_detection/candidates.csv").open(encoding="utf-8")))
    assert result["decisions_imported"] == 1 and result["unreviewed"] == 1
    assert rows[0]["first_reviewer"] == "Reviewer One" and rows[1]["first_decision"] == ""
    assert manifest[0]["source_page_url"] == original_url


@pytest.mark.parametrize("mutation,match", [
    ({"candidate_id": "unknown", "curator_decision": "include", "reviewed_at": "2026-08-23T10:00:00+00:00"}, "Unknown candidate"),
    ({"candidate_id": "candidate-0", "curator_decision": "maybe", "reviewed_at": "2026-08-23T10:00:00+00:00"}, "Invalid curator"),
    ({"candidate_id": "candidate-0", "curator_decision": "include", "reviewed_at": "not-a-time"}, "ISO-8601"),
    ({"candidate_id": "candidate-0", "curator_decision": "include", "reviewed_at": "2026-08-23T10:00:00+00:00", "license": "CC0"}, "unexpected fields"),
])
def test_offline_import_rejects_invalid_rows(tmp_path, mutation, match):
    config, candidates = _offline_fixture(tmp_path)
    receipt = _receipt(tmp_path / "receipt.json", candidates, [mutation])
    with pytest.raises(DetectionDatasetError, match=match):
        import_offline_review(config, receipt)


def test_offline_import_rejects_duplicate_and_missing_reviewer(tmp_path):
    config, candidates = _offline_fixture(tmp_path)
    decision = {"candidate_id": "candidate-0", "curator_decision": "include", "reviewed_at": "2026-08-23T10:00:00+00:00"}
    duplicate = _receipt(tmp_path / "duplicate.json", candidates, [decision, decision])
    with pytest.raises(DetectionDatasetError, match="Duplicate receipt"):
        import_offline_review(config, duplicate)
    missing = _receipt(tmp_path / "missing.json", candidates, [], reviewer="")
    with pytest.raises(DetectionDatasetError, match="Reviewer identity"):
        import_offline_review(config, missing)
