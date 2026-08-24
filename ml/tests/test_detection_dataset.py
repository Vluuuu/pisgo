from __future__ import annotations

import csv
import json
from pathlib import Path
import zipfile

import pytest
from PIL import Image

import pisgo_ml.detection_dataset as detection_dataset
from pisgo_ml.detection_dataset import (
    DetectionDatasetError,
    _completed_qa_categories,
    _candidate_set_digest,
    _final_curation_decision,
    _freeze_second_reviews,
    accepted_license,
    assign_detection_splits,
    collect_positive_expansion,
    export_negative_audit,
    export_negative_semantics_review,
    export_offline_review,
    import_negative_audit,
    import_negative_semantics_review,
    import_offline_review,
    parse_yolo_label,
    record_curation_decision,
    _stratified_negative_audit_sample,
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


def test_negative_audit_sample_is_deterministic_and_covers_each_query():
    candidates = [
        {
            "image_id": f"candidate-{query}-{number}",
            "candidate_role": "hard_negative_candidate",
            "search_query": query,
        }
        for query, count in (("leaves", 20), ("flowers", 12), ("fruit", 8))
        for number in range(count)
    ]
    rows = [
        {
            "image_id": candidate["image_id"],
            "first_decision": "exclude",
            "second_required": "",
        }
        for candidate in candidates
    ]

    first = _stratified_negative_audit_sample(
        candidates, rows, sample_size=10, seed=42
    )
    second = _stratified_negative_audit_sample(
        candidates, rows, sample_size=10, seed=42
    )

    assert [row["image_id"] for row in first] == [row["image_id"] for row in second]
    assert len(first) == 10
    assert {row["search_query"] for row in first} == {"leaves", "flowers", "fruit"}


def test_negative_audit_sample_uses_only_final_excluded_hard_negatives():
    candidates = [
        {"image_id": "excluded", "candidate_role": "hard_negative_candidate", "search_query": "leaves"},
        {"image_id": "included", "candidate_role": "hard_negative_candidate", "search_query": "leaves"},
        {"image_id": "positive", "candidate_role": "positive_candidate", "search_query": "banana"},
    ]
    rows = [
        {"image_id": "excluded", "first_decision": "exclude", "second_required": ""},
        {"image_id": "included", "first_decision": "include", "second_required": ""},
        {"image_id": "positive", "first_decision": "exclude", "second_required": ""},
    ]

    assert _stratified_negative_audit_sample(
        candidates, rows, sample_size=1, seed=42
    ) == [candidates[0]]


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


@pytest.mark.parametrize(
    "semantics_decision,expected",
    [
        ("include_as_negative", "include"),
        ("exclude_as_unusable", "exclude"),
        ("needs_review", "needs_review"),
    ],
)
def test_final_curation_decision_applies_explicit_semantics_overlay(
    semantics_decision, expected
):
    assert (
        _final_curation_decision(
            {
                "first_decision": "exclude",
                "second_required": "",
                "semantics_decision": semantics_decision,
            }
        )
        == expected
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
        "  report_markdown: datasets/processed/audit.md\nsource:\n"
        "  accepted_license_prefixes: [CC0, CC BY, CC BY-SA]\n"
        "  accepted_mime_types: [image/jpeg, image/png, image/webp]\n"
        "  max_file_bytes: 12582912\n"
        "  targets:\n    positive_candidate: 2\n"
        "data:\n  near_duplicate_hamming_distance: 3\n",
        encoding="utf-8",
    )
    return config, candidates


def _enable_positive_expansion(config: Path, *, target: int = 1) -> None:
    with config.open("a", encoding="utf-8") as handle:
        handle.write(
            "positive_expansion:\n"
            f"  new_candidate_target: {target}\n"
            "  queries:\n"
            f"    - text: expansion banana\n      max_accepts: {target}\n"
        )


def _commons_page_fixture(
    page_id: int,
    *,
    title: str | None = None,
    license_name: str = "CC BY 4.0",
    author: str = "Collector",
    license_url: str = "https://creativecommons.org/licenses/by/4.0",
) -> dict:
    return {
        "pageid": page_id,
        "title": title or f"File:expansion-{page_id}.jpg",
        "imageinfo": [
            {
                "mime": "image/jpeg",
                "size": 100,
                "url": f"https://example.test/expansion-{page_id}.jpg",
                "extmetadata": {
                    "LicenseShortName": {"value": license_name},
                    "Artist": {"value": author},
                    "LicenseUrl": {"value": license_url},
                },
            }
        ],
    }


def _fake_download_factory(colors: dict[str, tuple[int, int, int]]):
    def fake_download(url, destination, config):
        color = colors[url]
        Image.new("RGB", (24, 16), color).save(destination)
        return detection_dataset._sha256_file(destination), destination.stat().st_size

    return fake_download


def _receipt(
    path: Path,
    candidates: list[dict[str, str]],
    decisions: list[dict[str, str]],
    reviewer: str = "Reviewer One",
    review_id: str = "review-one",
) -> Path:
    path.write_text(json.dumps({
        "version": 1, "review_id": review_id, "bundle_digest": _candidate_set_digest(candidates),
        "reviewer": reviewer, "decisions": decisions,
    }), encoding="utf-8")
    return path


def test_negative_audit_export_and_import_do_not_change_curation(tmp_path):
    config, candidates = _offline_fixture(tmp_path)
    record_curation_decision(
        config,
        image_id=candidates[0]["image_id"],
        stage="first",
        decision="include",
        reviewer="Reviewer One",
    )
    record_curation_decision(
        config,
        image_id=candidates[1]["image_id"],
        stage="first",
        decision="exclude",
        reviewer="Reviewer One",
    )
    result = export_negative_audit(config, "negative-audit", sample_size=1)
    export_path = Path(result["path"])
    manifest = json.loads((export_path / "audit_manifest.json").read_text(encoding="utf-8"))
    curation_path = config.parent.parent / "datasets/raw/banana_bunch_detection/curation.csv"
    before = curation_path.read_bytes()
    receipt = tmp_path / "negative-audit-receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "version": 1,
                "audit_id": "negative-audit",
                "sample_digest": manifest["sample_digest"],
                "reviewer": "Auditor Two",
                "decisions": [
                    {
                        "candidate_id": candidates[1]["image_id"],
                        "audit_decision": "recommend_re_review",
                        "reason": "useful_hard_negative",
                        "notes": "Useful banana-free vegetation.",
                        "reviewed_at": "2026-08-24T10:00:00+00:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = import_negative_audit(config, receipt)

    assert report["recommended_for_re_review"] == 1
    assert report["semantic_misunderstanding_detected"] is True
    assert report["curation_decisions_changed"] is False
    assert curation_path.read_bytes() == before


def test_negative_audit_import_requires_a_complete_sample(tmp_path):
    config, candidates = _offline_fixture(tmp_path)
    for candidate, decision in zip(candidates, ("include", "exclude")):
        record_curation_decision(
            config,
            image_id=candidate["image_id"],
            stage="first",
            decision=decision,
            reviewer="Reviewer One",
        )
    result = export_negative_audit(config, "negative-audit", sample_size=1)
    manifest = json.loads(
        (Path(result["path"]) / "audit_manifest.json").read_text(encoding="utf-8")
    )
    receipt = tmp_path / "negative-audit-receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "version": 1,
                "audit_id": "negative-audit",
                "sample_digest": manifest["sample_digest"],
                "reviewer": "Auditor Two",
                "decisions": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DetectionDatasetError, match="incomplete"):
        import_negative_audit(config, receipt)


def _semantics_source_audit(
    config: Path, candidates: list[dict[str, str]], count: int
) -> str:
    audit_id = "full-negative-audit"
    export_path = config.parent.parent / "datasets/local_review_exports" / audit_id
    export_path.mkdir(parents=True)
    hard_negative = candidates[1]
    manifest_candidates = [
        {
            "candidate_id": f"negative-{number}",
            "search_query": "leaves",
            "source_page_url": hard_negative["source_page_url"],
            "author": hard_negative["author"],
            "license": hard_negative["license"],
            "sha256": hard_negative["sha256"],
            "image_file": f"images/negative-{number}.jpg",
        }
        for number in range(count)
    ]
    manifest_candidates[0]["candidate_id"] = hard_negative["image_id"]
    decisions = [
        {
            "candidate_id": row["candidate_id"],
            "audit_decision": "confirmed_exclusion",
            "reason": "useful_hard_negative",
            "notes": "",
            "reviewed_at": "2026-08-24T10:00:00+00:00",
        }
        for row in manifest_candidates
    ]
    (export_path / "audit_manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "audit_id": audit_id,
                "sample_size": count,
                "candidates": manifest_candidates,
            }
        ),
        encoding="utf-8",
    )
    (export_path / "audit_report.json").write_text(
        json.dumps(
            {
                "audit_id": audit_id,
                "sample_size": count,
                "decisions": decisions,
            }
        ),
        encoding="utf-8",
    )
    return audit_id


def test_negative_semantics_import_preserves_history_and_provenance(
    tmp_path, monkeypatch
):
    config, candidates = _offline_fixture(tmp_path)
    record_curation_decision(
        config,
        image_id=candidates[0]["image_id"],
        stage="first",
        decision="include",
        reviewer="Reviewer One",
    )
    record_curation_decision(
        config,
        image_id=candidates[1]["image_id"],
        stage="first",
        decision="exclude",
        reviewer="Reviewer One",
    )
    monkeypatch.setattr(detection_dataset, "NEGATIVE_SEMANTICS_TARGET_COUNT", 1)
    audit_id = _semantics_source_audit(config, candidates, 1)
    approval_path = config.parent.parent / "datasets/raw/banana_bunch_detection/curation_approval.json"
    approval_path.write_text(
        json.dumps(
            {
                "approved_by": "Approver",
                "approved_at": "2026-08-24T10:00:00+00:00",
                "manifest_sha256": "old",
                "curation_sha256": "old",
            }
        ),
        encoding="utf-8",
    )
    result = export_negative_semantics_review(config, "semantics-review", audit_id)
    export_path = Path(result["path"])
    semantics_manifest = json.loads(
        (export_path / "semantics_manifest.json").read_text(encoding="utf-8")
    )
    html_text = (export_path / "index.html").read_text(encoding="utf-8")
    assert "include_as_negative" in html_text
    assert "confirmed_exclusion" not in html_text

    curation_path = config.parent.parent / "datasets/raw/banana_bunch_detection/curation.csv"
    before_candidates = list(
        csv.DictReader(
            (config.parent.parent / "datasets/raw/banana_bunch_detection/candidates.csv").open(
                encoding="utf-8"
            )
        )
    )
    before_curation = list(csv.DictReader(curation_path.open(encoding="utf-8")))
    receipt = tmp_path / "semantics-receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "version": 1,
                "review_id": "semantics-review",
                "bundle_digest": semantics_manifest["bundle_digest"],
                "reviewer": "Semantics Reviewer",
                "decisions": [
                    {
                        "candidate_id": candidates[1]["image_id"],
                        "semantics_decision": "include_as_negative",
                        "reviewed_at": "2026-08-24T11:00:00+00:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = import_negative_semantics_review(config, receipt)

    after_candidates = list(
        csv.DictReader(
            (config.parent.parent / "datasets/raw/banana_bunch_detection/candidates.csv").open(
                encoding="utf-8"
            )
        )
    )
    after_curation = list(csv.DictReader(curation_path.open(encoding="utf-8")))
    assert report["include_as_negative"] == 1
    assert report["resulting_cumulative_hard_negative_include_count"] == 1
    assert report["approval_valid"] is False
    assert report["new_cumulative_approval_required"] is True
    assert not approval_path.exists()
    assert before_candidates[0] == after_candidates[0]
    assert all(
        before_candidates[1][field] == after_candidates[1][field]
        for field in before_candidates[1]
        if field != "curator_decision"
    )
    assert all(
        before_curation[1][field] == after_curation[1][field]
        for field in detection_dataset.CURATION_HISTORY_FIELDS
        if field != "final_decision"
    )
    assert after_curation[1]["semantics_decision"] == "include_as_negative"
    assert after_curation[1]["semantics_reviewer"] == "Semantics Reviewer"


def test_negative_semantics_import_requires_exact_complete_set(tmp_path, monkeypatch):
    config, candidates = _offline_fixture(tmp_path)
    for candidate, decision in zip(candidates, ("include", "exclude")):
        record_curation_decision(
            config,
            image_id=candidate["image_id"],
            stage="first",
            decision=decision,
            reviewer="Reviewer One",
        )
    monkeypatch.setattr(detection_dataset, "NEGATIVE_SEMANTICS_TARGET_COUNT", 1)
    audit_id = _semantics_source_audit(config, candidates, 1)
    result = export_negative_semantics_review(config, "semantics-review", audit_id)
    manifest = json.loads(
        (Path(result["path"]) / "semantics_manifest.json").read_text(encoding="utf-8")
    )
    receipt = tmp_path / "semantics-receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "version": 1,
                "review_id": "semantics-review",
                "bundle_digest": manifest["bundle_digest"],
                "reviewer": "Reviewer",
                "decisions": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DetectionDatasetError, match="incomplete"):
        import_negative_semantics_review(config, receipt)


def test_positive_expansion_appends_pending_rows_and_preserves_history(
    tmp_path, monkeypatch
):
    config, candidates = _offline_fixture(tmp_path)
    _enable_positive_expansion(config, target=2)
    for candidate, decision in zip(candidates, ("include", "exclude")):
        record_curation_decision(
            config,
            image_id=candidate["image_id"],
            stage="first",
            decision=decision,
            reviewer="Reviewer One",
        )
    project = config.parent.parent
    manifest_path = project / "datasets/raw/banana_bunch_detection/candidates.csv"
    curation_path = manifest_path.with_name("curation.csv")
    approval_path = manifest_path.with_name("curation_approval.json")
    approval_path.write_text(
        json.dumps(
            {
                "approved_by": "Approver",
                "approved_at": "2026-08-24T10:00:00+00:00",
                "manifest_sha256": detection_dataset._sha256_file(manifest_path),
                "curation_sha256": detection_dataset._sha256_file(curation_path),
            }
        ),
        encoding="utf-8",
    )
    before_candidates = list(csv.DictReader(manifest_path.open(encoding="utf-8")))
    before_curation = list(csv.DictReader(curation_path.open(encoding="utf-8")))
    pages = [
        _commons_page_fixture(10),
        _commons_page_fixture(11),
        _commons_page_fixture(12, license_name="Copyrighted"),
        _commons_page_fixture(13, author=""),
    ]
    monkeypatch.setattr(detection_dataset, "_search_pages", lambda config, query: pages)
    monkeypatch.setattr(
        detection_dataset,
        "_download",
        _fake_download_factory(
            {
                "https://example.test/expansion-10.jpg": (200, 20, 20),
                "https://example.test/expansion-11.jpg": (20, 20, 200),
            }
        ),
    )
    monkeypatch.setattr(
        detection_dataset,
        "_perceptual_hash",
        lambda path: (
            "f000000000000000" if "10" in path.stem else "0f00000000000000",
            24,
            16,
        ),
    )

    result = collect_positive_expansion(config, "positive-batch")

    after_candidates = list(csv.DictReader(manifest_path.open(encoding="utf-8")))
    after_curation = list(csv.DictReader(curation_path.open(encoding="utf-8")))
    assert after_candidates[:2] == before_candidates
    assert after_curation[:2] == before_curation
    assert [row["image_id"] for row in after_candidates[2:]] == [
        "commons-10",
        "commons-11",
    ]
    assert all(row["candidate_role"] == "positive_candidate" for row in after_candidates[2:])
    assert all(row["is_augmented"] == "false" for row in after_candidates[2:])
    assert all(row["curator_decision"] == "pending" for row in after_candidates[2:])
    assert all(
        not value for row in after_curation[2:] for field, value in row.items() if field != "image_id"
    )
    assert not approval_path.exists()
    assert result["candidate_count"] == 2
    assert result["baseline_state"]["approval"]["approved_by"] == "Approver"
    assert result["target_met"] is True


def test_positive_expansion_deduplicates_and_reports_rejections(tmp_path, monkeypatch):
    config, candidates = _offline_fixture(tmp_path)
    _enable_positive_expansion(config)
    detection_dataset._write_curation_state(
        detection_dataset.load_detection_config(config),
        detection_dataset._read_csv(
            config.parent.parent
            / "datasets/raw/banana_bunch_detection/candidates.csv"
        ),
        detection_dataset._empty_curation_rows(candidates),
    )
    duplicate_source = _commons_page_fixture(
        20, title=candidates[0]["source_item_id"]
    )
    exact_content = _commons_page_fixture(21)
    near_content = _commons_page_fixture(22)
    licensed_out = _commons_page_fixture(23, license_name="Copyrighted")
    no_author = _commons_page_fixture(24, author="")
    accepted = _commons_page_fixture(25)
    pages = [
        duplicate_source,
        exact_content,
        near_content,
        licensed_out,
        no_author,
        accepted,
    ]
    monkeypatch.setattr(detection_dataset, "_search_pages", lambda config, query: pages)
    existing_image = config.parent.parent / candidates[0]["local_path"]

    def fake_download(url, destination, config):
        if url.endswith("21.jpg"):
            destination.write_bytes(existing_image.read_bytes())
        else:
            Image.new("RGB", (24, 16), (100, 40, int(destination.stem.split("-")[-1]))).save(
                destination
            )
        return detection_dataset._sha256_file(destination), destination.stat().st_size

    monkeypatch.setattr(detection_dataset, "_download", fake_download)

    def fake_phash(path):
        if path.stem.endswith("22"):
            return candidates[0]["perceptual_hash"], 24, 16
        return "f000000000000000", 24, 16

    monkeypatch.setattr(detection_dataset, "_perceptual_hash", fake_phash)

    result = collect_positive_expansion(config, "dedupe-batch")

    assert result["candidate_ids"] == ["commons-25"]
    assert result["duplicate_removals"] == {
        "exact_source": 1,
        "exact_content": 1,
        "near_duplicate": 1,
    }
    assert result["provenance_license_rejections"] == {
        "license": 1,
        "provenance": 1,
    }


def test_positive_expansion_rolls_back_state_and_images(tmp_path, monkeypatch):
    config, _ = _offline_fixture(tmp_path)
    _enable_positive_expansion(config)
    project = config.parent.parent
    manifest_path = project / "datasets/raw/banana_bunch_detection/candidates.csv"
    curation_path = manifest_path.with_name("curation.csv")
    detection_dataset._write_curation_state(
        detection_dataset.load_detection_config(config),
        detection_dataset._read_csv(manifest_path),
        detection_dataset._empty_curation_rows(detection_dataset._read_csv(manifest_path)),
    )
    approval_path = manifest_path.with_name("curation_approval.json")
    approval_path.write_text('{"approved_by":"human"}', encoding="utf-8")
    before = {
        path: path.read_bytes() for path in (manifest_path, curation_path, approval_path)
    }
    page = _commons_page_fixture(30)
    monkeypatch.setattr(detection_dataset, "_search_pages", lambda config, query: [page])
    monkeypatch.setattr(
        detection_dataset,
        "_download",
        _fake_download_factory({"https://example.test/expansion-30.jpg": (220, 60, 40)}),
    )
    monkeypatch.setattr(
        detection_dataset,
        "_perceptual_hash",
        lambda path: ("f000000000000000", 24, 16),
    )
    original_write_json = detection_dataset.write_json

    def failing_write_json(payload, path):
        if Path(path).name == "batch_manifest.json":
            raise OSError("simulated report failure")
        return original_write_json(payload, path)

    monkeypatch.setattr(detection_dataset, "write_json", failing_write_json)

    with pytest.raises(OSError, match="simulated"):
        collect_positive_expansion(config, "rollback-batch")

    assert all(path.read_bytes() == content for path, content in before.items())
    assert not (project / "datasets/raw/banana_bunch_detection/images/commons-30.jpg").exists()
    assert not (
        project
        / "datasets/raw/banana_bunch_detection/expansion_batches/rollback-batch"
    ).exists()


def test_batch_offline_export_contains_only_new_ids_and_valid_hashes(
    tmp_path, monkeypatch
):
    config, candidates = _offline_fixture(tmp_path)
    _enable_positive_expansion(config)
    for candidate, decision in zip(candidates, ("include", "exclude")):
        record_curation_decision(
            config,
            image_id=candidate["image_id"],
            stage="first",
            decision=decision,
            reviewer="Reviewer One",
        )
    curation_path = (
        config.parent.parent
        / "datasets/raw/banana_bunch_detection/curation.csv"
    )
    rows = list(csv.DictReader(curation_path.open(encoding="utf-8")))
    rows[0]["second_required"] = "true"
    rows[0]["second_reason"] = "spot_check"
    detection_dataset._write_csv(curation_path, rows, detection_dataset.CURATION_FIELDS)
    page = _commons_page_fixture(40)
    monkeypatch.setattr(detection_dataset, "_search_pages", lambda config, query: [page])
    monkeypatch.setattr(
        detection_dataset,
        "_download",
        _fake_download_factory({"https://example.test/expansion-40.jpg": (10, 210, 80)}),
    )
    monkeypatch.setattr(
        detection_dataset,
        "_perceptual_hash",
        lambda path: ("f000000000000000", 24, 16),
    )
    collect_positive_expansion(config, "review-batch")

    result = export_offline_review(
        config, "review-batch-reviewer-one", batch_id="review-batch"
    )
    review_path = Path(result["path"])
    manifest = json.loads((review_path / "review_manifest.json").read_text(encoding="utf-8"))
    assert result["bundle_validated"] is True
    assert [row["candidate_id"] for row in manifest["candidates"]] == ["commons-40"]
    assert all(row["candidate_id"] not in {c["image_id"] for c in candidates} for row in manifest["candidates"])
    receipt = _receipt(
        tmp_path / "batch-receipt.json",
        [
            {
                "image_id": row["candidate_id"],
                "sha256": row["source_sha256"],
            }
            for row in manifest["candidates"]
        ],
        [
            {
                "candidate_id": "commons-40",
                "curator_decision": "include",
                "reviewed_at": "2026-08-24T15:21:36+00:00",
            }
        ],
        review_id="review-batch-reviewer-one",
    )
    imported = import_offline_review(config, receipt)
    rows = list(csv.DictReader(curation_path.open(encoding="utf-8")))
    imported_row = next(row for row in rows if row["image_id"] == "commons-40")
    assert imported["decisions_imported"] == 1
    assert imported_row["first_decision"] == "include"
    assert imported_row["second_required"] == "true"
    assert imported_row["second_reason"] == "spot_check"
    exported = manifest["candidates"][0]
    assert detection_dataset._sha256_file(review_path / exported["image_file"]) == exported[
        "review_image_sha256"
    ]
    with zipfile.ZipFile(result["archive"]) as handle:
        assert exported["image_file"] in handle.namelist()


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
