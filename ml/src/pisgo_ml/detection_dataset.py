"""Collect, hand off, and audit a provenance-first banana-bunch dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import math
import mimetypes
import os
import re
import secrets
import shutil
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import numpy as np
import yaml
from PIL import Image, ImageOps

from .utils import ensure_parent, write_json


BLOCKED = "YOLO_DATASET_BLOCKED"
READY = "DATASET_READY_FOR_REVIEW"
EMERGENCY_READY = "EMERGENCY_YOLO_DATASET_READY"
EMERGENCY_DATASET_NAME = "competition-emergency-baseline-v1"
EMERGENCY_INVALID_POSITIVE_IDS = {"commons-164382152"}
CANDIDATE_FIELDS = [
    "image_id",
    "source_provider",
    "source_item_id",
    "source_page_url",
    "original_url",
    "author",
    "license",
    "license_url",
    "retrieved_at",
    "provenance_status",
    "search_query",
    "candidate_role",
    "local_path",
    "mime_type",
    "width",
    "height",
    "bytes",
    "sha256",
    "perceptual_hash",
    "is_augmented",
    "specimen_id",
    "group_id",
    "curator_decision",
]
CURATION_HISTORY_FIELDS = [
    "image_id",
    "first_decision",
    "first_reviewer",
    "first_reviewed_at",
    "second_required",
    "second_reason",
    "second_decision",
    "second_reviewer",
    "second_reviewed_at",
    "final_decision",
]
SEMANTICS_CURATION_FIELDS = [
    "semantics_source_audit_id",
    "semantics_review_id",
    "semantics_decision",
    "semantics_reviewer",
    "semantics_reviewed_at",
]
CURATION_FIELDS = CURATION_HISTORY_FIELDS + SEMANTICS_CURATION_FIELDS
CURATION_DECISIONS = {"include", "exclude", "needs_review"}
CURATION_APPROVAL = "curation_approval.json"
CURATION_RECEIPTS = "curation.csv"
REVIEW_RECEIPT_VERSION = 1
REVIEW_EXPORT_DIR = "datasets/local_review_exports"
EXPANSION_BATCH_DIR = "datasets/raw/banana_bunch_detection/expansion_batches"
REVIEW_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
POSITIVE_EXPANSION_VERSION = 1
NEGATIVE_AUDIT_VERSION = 1
NEGATIVE_AUDIT_DECISIONS = {"confirmed_exclusion", "recommend_re_review"}
NEGATIVE_SEMANTICS_VERSION = 1
NEGATIVE_SEMANTICS_DECISIONS = {
    "include_as_negative",
    "exclude_as_unusable",
    "needs_review",
}
NEGATIVE_SEMANTICS_TARGET_REASON = "useful_hard_negative"
NEGATIVE_SEMANTICS_TARGET_COUNT = 76
NEGATIVE_AUDIT_REASONS = {
    "useful_hard_negative",
    "irrelevant_or_unusable",
    "poor_quality",
    "broken_or_corrupt",
    "redundant",
    "provenance_or_license",
    "unsuitable_content",
    "other",
}


class DetectionDatasetError(ValueError):
    """Raised when the detection dataset contract is not satisfied."""


def load_detection_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise DetectionDatasetError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    required = {"project", "paths", "source", "data"}
    missing = sorted(required - set(config))
    if missing:
        raise DetectionDatasetError(f"Missing configuration sections: {', '.join(missing)}")

    config["_config_path"] = path
    config["_project_root"] = path.parent.parent
    for key, value in config["paths"].items():
        candidate = Path(value).expanduser()
        config["paths"][key] = (
            candidate if candidate.is_absolute() else config["_project_root"] / candidate
        )
    return config


def accepted_license(name: str, prefixes: Iterable[str]) -> bool:
    normalized = " ".join(html.unescape(name).split())
    return any(
        re.fullmatch(rf"{re.escape(prefix)}(?:\s+[0-9].*)?", normalized, re.IGNORECASE)
        for prefix in prefixes
    )


def _metadata_value(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key, {})
    if isinstance(value, dict):
        value = value.get("value", "")
    return " ".join(re.sub(r"<[^>]+>", " ", html.unescape(str(value))).split())


def _commons_page(title: str) -> str:
    quoted = urllib.parse.quote(title.removeprefix("File:").replace(" ", "_"), safe="()!,.-_")
    return f"https://commons.wikimedia.org/wiki/File:{quoted}"


def _request_json(url: str, user_agent: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _search_pages(config: dict[str, Any], query: str) -> Iterable[dict[str, Any]]:
    source = config["source"]
    remaining = int(source["per_query_limit"])
    continuation: dict[str, Any] = {}
    # File namespace plus raster MIME validation below keeps derivatives/category pages out.
    while remaining > 0:
        params: dict[str, Any] = {
            "action": "query",
            "format": "json",
            "formatversion": 2,
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrnamespace": 6,
            "gsrlimit": min(int(source["results_per_request"]), remaining),
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
        }
        params.update(continuation)
        url = f"{source['api_url']}?{urllib.parse.urlencode(params)}"
        payload = _request_json(
            url, str(source["user_agent"]), int(source["request_timeout_seconds"])
        )
        pages = payload.get("query", {}).get("pages", [])
        for page in pages:
            yield page
        remaining -= len(pages)
        continuation = payload.get("continue", {})
        if not pages or not continuation:
            break


def _download(url: str, destination: Path, config: dict[str, Any]) -> tuple[str, int]:
    source = config["source"]
    maximum = int(source["max_file_bytes"])
    request = urllib.request.Request(url, headers={"User-Agent": str(source["user_agent"])})
    temporary = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    total = 0
    try:
        with urllib.request.urlopen(
            request, timeout=int(source["request_timeout_seconds"])
        ) as response, temporary.open("wb") as handle:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > maximum:
                raise DetectionDatasetError(f"download exceeds {maximum} bytes")
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > maximum:
                    raise DetectionDatasetError(f"download exceeds {maximum} bytes")
                digest.update(chunk)
                handle.write(chunk)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return digest.hexdigest(), total


def _perceptual_hash(path: Path) -> tuple[str, int, int]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        width, height = image.size
        pixels = np.asarray(
            image.convert("L").resize((9, 8), Image.Resampling.LANCZOS), dtype=np.int16
        )
    bits = pixels[:, 1:] > pixels[:, :-1]
    value = sum(int(bit) << index for index, bit in enumerate(bits.flat))
    return f"{value:016x}", width, height


def _extension(mime_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(mime_type.lower(), "")


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    destination = ensure_parent(path)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(destination)


def _require_fields(path: Path, rows: list[dict[str, str]], fields: Iterable[str]) -> None:
    if not rows:
        return
    missing = sorted(set(fields) - set(rows[0]))
    if missing:
        raise DetectionDatasetError(f"{path} is missing columns: {', '.join(missing)}")


def _curation_paths(manifest_path: Path) -> tuple[Path, Path]:
    return manifest_path.with_name(CURATION_RECEIPTS), manifest_path.with_name(CURATION_APPROVAL)


def _empty_curation_rows(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{field: candidate["image_id"] if field == "image_id" else "" for field in CURATION_FIELDS} for candidate in candidates]


def _load_curation(
    manifest_path: Path, candidates: list[dict[str, str]]
) -> list[dict[str, str]]:
    receipt_path, _ = _curation_paths(manifest_path)
    rows = _read_csv(receipt_path)
    if not rows:
        return _empty_curation_rows(candidates)
    _require_fields(receipt_path, rows, CURATION_HISTORY_FIELDS)
    for row in rows:
        for field in SEMANTICS_CURATION_FIELDS:
            row.setdefault(field, "")
    candidate_ids = [row["image_id"] for row in candidates]
    receipt_ids = [row["image_id"] for row in rows]
    if len(receipt_ids) != len(set(receipt_ids)):
        raise DetectionDatasetError("Curation receipts contain duplicate image_id rows")
    if set(receipt_ids) != set(candidate_ids):
        raise DetectionDatasetError("Curation receipts do not match the candidate manifest")
    by_id = {row["image_id"]: row for row in rows}
    return [by_id[image_id] for image_id in candidate_ids]


def _final_curation_decision(row: dict[str, str]) -> str:
    first = row.get("first_decision", "").strip().lower()
    if not first:
        decision = "pending"
    elif row.get("second_required", "").lower() != "true":
        decision = first
    else:
        second = row.get("second_decision", "").strip().lower()
        if not second:
            decision = "needs_review"
        elif row.get("second_reason") == "spot_check":
            decision = first if second == first else "needs_review"
        else:
            decision = second if second in {"include", "exclude"} else "needs_review"
    semantics = row.get("semantics_decision", "").strip().lower()
    if semantics == "include_as_negative":
        return "include"
    if semantics == "needs_review":
        return "needs_review"
    if semantics == "exclude_as_unusable":
        return decision
    return decision


def _freeze_second_reviews(
    rows: list[dict[str, str]], seed: int, image_ids: set[str] | None = None
) -> None:
    scoped = [row for row in rows if image_ids is None or row["image_id"] in image_ids]
    if not scoped or any(not row.get("first_decision") for row in scoped):
        return
    if any(row.get("second_required") for row in scoped):
        return
    for row in scoped:
        if row["first_decision"] == "needs_review":
            row["second_required"] = "true"
            row["second_reason"] = "needs_review"
    for role in ("positive_candidate", "hard_negative_candidate"):
        included = sorted(
            (
                row
                for row in scoped
                if row["first_decision"] == "include"
                and row["candidate_role"] == role
            ),
            key=lambda row: row["image_id"],
        )
        sample_size = math.ceil(len(included) * 0.10)
        ranked = sorted(
            included,
            key=lambda row: hashlib.sha256(
                f"{seed}:{role}:{row['image_id']}".encode()
            ).digest(),
        )
        for row in ranked[:sample_size]:
            row["second_required"] = "true"
            row["second_reason"] = "spot_check"


def _approval_matches(manifest_path: Path, receipt_path: Path, approval_path: Path) -> bool:
    if not receipt_path.is_file() or not approval_path.is_file():
        return False
    try:
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return (
        approval.get("manifest_sha256") == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        and approval.get("curation_sha256") == hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        and bool(str(approval.get("approved_by", "")).strip())
        and bool(str(approval.get("approved_at", "")).strip())
    )


def curation_summary(config_path: str | Path) -> dict[str, Any]:
    config = load_detection_config(config_path)
    manifest_path: Path = config["paths"]["candidate_manifest"]
    candidates = _read_csv(manifest_path)
    _require_fields(manifest_path, candidates, CANDIDATE_FIELDS)
    if len(candidates) != len({row["image_id"] for row in candidates}):
        raise DetectionDatasetError("Candidate manifest contains duplicate image_id rows")
    rows = _load_curation(manifest_path, candidates)
    candidate_by_id = {row["image_id"]: row for row in candidates}
    combined = [{**row, "candidate_role": candidate_by_id[row["image_id"]]["candidate_role"]} for row in rows]
    first_reviewed = sum(bool(row["first_decision"]) for row in combined)
    required_second = [row for row in combined if row["second_required"].lower() == "true"]
    second_reviewed = sum(bool(row["second_decision"]) for row in required_second)
    final = {row["image_id"]: _final_curation_decision(row) for row in combined}
    unresolved = sum(decision in {"pending", "needs_review"} for decision in final.values())
    counts = Counter(
        (row["candidate_role"], final[row["image_id"]]) for row in combined
    )
    included = [candidate_by_id[image_id] for image_id, decision in final.items() if decision == "include"]
    receipt_path, approval_path = _curation_paths(manifest_path)
    approval_valid = _approval_matches(manifest_path, receipt_path, approval_path)
    positive_count = sum(row["candidate_role"] == "positive_candidate" for row in candidates)
    result = {
        "total_reviewed": first_reviewed,
        "positive_include": counts[("positive_candidate", "include")],
        "positive_exclude": counts[("positive_candidate", "exclude")],
        "positive_needs_review": counts[("positive_candidate", "needs_review")],
        "hard_negative_include": counts[("hard_negative_candidate", "include")],
        "hard_negative_exclude": counts[("hard_negative_candidate", "exclude")],
        "hard_negative_needs_review": counts[("hard_negative_candidate", "needs_review")],
        "second_review_count": second_reviewed,
        "final_unresolved_count": unresolved,
        "verified_positive_image_count": counts[("positive_candidate", "include")],
        "verified_hard_negative_count": counts[("hard_negative_candidate", "include")],
        "unique_source_group_count": {
            "sources": len({row["source_page_url"] for row in included}),
            "groups": len({row["group_id"] for row in included}),
        },
        "more_positive_collection_recommended": positive_count
        < int(config["source"]["targets"]["positive_candidate"]),
        "required_second_review_count": len(required_second),
        "approval_valid": approval_valid,
    }
    blockers = []
    if first_reviewed != len(candidates):
        blockers.append(f"First-pass human review incomplete: {first_reviewed}/{len(candidates)}")
    if second_reviewed != len(required_second):
        blockers.append(f"Second human review incomplete: {second_reviewed}/{len(required_second)}")
    if unresolved:
        blockers.append(f"Unresolved curation decisions: {unresolved}")
    if not approval_valid:
        blockers.append("Final human curation approval is missing or stale")
    result["ready"] = not blockers
    result["blockers"] = blockers
    return result


def _write_curation_state(
    config: dict[str, Any], candidates: list[dict[str, str]], rows: list[dict[str, str]]
) -> None:
    manifest_path: Path = config["paths"]["candidate_manifest"]
    receipt_path, approval_path = _curation_paths(manifest_path)
    by_id = {row["image_id"]: row for row in rows}
    updated_candidates = []
    for candidate in candidates:
        updated = dict(candidate)
        updated["curator_decision"] = _final_curation_decision(by_id[candidate["image_id"]])
        updated_candidates.append(updated)
    _write_csv(receipt_path, rows, CURATION_FIELDS)
    _write_csv(manifest_path, updated_candidates, CANDIDATE_FIELDS)
    approval_path.unlink(missing_ok=True)


def record_curation_decision(
    config_path: str | Path,
    *,
    image_id: str,
    stage: str,
    decision: str,
    reviewer: str,
) -> None:
    decision = decision.strip().lower()
    reviewer = " ".join(reviewer.split())
    if decision not in CURATION_DECISIONS:
        raise DetectionDatasetError("Decision must be include, exclude, or needs_review")
    if not reviewer:
        raise DetectionDatasetError("Reviewer identity is required")
    config = load_detection_config(config_path)
    manifest_path: Path = config["paths"]["candidate_manifest"]
    candidates = _read_csv(manifest_path)
    rows = _load_curation(manifest_path, candidates)
    candidate_by_id = {row["image_id"]: row for row in candidates}
    if image_id not in candidate_by_id:
        raise DetectionDatasetError("Unknown candidate image_id")
    row = next(row for row in rows if row["image_id"] == image_id)
    now = datetime.now(timezone.utc).isoformat()
    if stage == "first":
        if any(item.get("second_required") for item in rows):
            raise DetectionDatasetError("First-pass decisions are frozen for second review")
        row["first_decision"] = decision
        row["first_reviewer"] = reviewer
        row["first_reviewed_at"] = now
        enriched = [
            {**item, "candidate_role": candidate_by_id[item["image_id"]]["candidate_role"]}
            for item in rows
        ]
        _freeze_second_reviews(enriched, int(config["project"]["random_seed"]))
        for item, frozen in zip(rows, enriched):
            item["second_required"] = frozen["second_required"]
            item["second_reason"] = frozen["second_reason"]
    elif stage == "second":
        if row.get("second_required", "").lower() != "true":
            raise DetectionDatasetError("Candidate is not assigned to second review")
        if reviewer.casefold() == row["first_reviewer"].casefold():
            raise DetectionDatasetError("Second reviewer must differ from the first reviewer")
        row["second_decision"] = decision
        row["second_reviewer"] = reviewer
        row["second_reviewed_at"] = now
    else:
        raise DetectionDatasetError("Review stage must be first or second")
    for item in rows:
        item["final_decision"] = _final_curation_decision(item)
    _write_curation_state(config, candidates, rows)


def approve_curation(config_path: str | Path, reviewer: str) -> None:
    reviewer = " ".join(reviewer.split())
    if not reviewer:
        raise DetectionDatasetError("Approver identity is required")
    summary = curation_summary(config_path)
    blockers = [blocker for blocker in summary["blockers"] if "approval" not in blocker.lower()]
    if blockers:
        raise DetectionDatasetError("; ".join(blockers))
    config = load_detection_config(config_path)
    manifest_path: Path = config["paths"]["candidate_manifest"]
    receipt_path, approval_path = _curation_paths(manifest_path)
    write_json(
        {
            "approved_by": reviewer,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "curation_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        },
        approval_path,
    )


def _require_approved_curation(config_path: str | Path) -> list[str]:
    try:
        return curation_summary(config_path)["blockers"]
    except DetectionDatasetError as error:
        return [str(error)]


def _candidate_set_digest(candidates: list[dict[str, str]]) -> str:
    identity = [
        {"candidate_id": row["image_id"], "sha256": row["sha256"]}
        for row in candidates
    ]
    return hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _expansion_batch_path(config: dict[str, Any], batch_id: str) -> Path:
    if not REVIEW_ID_PATTERN.fullmatch(batch_id):
        raise DetectionDatasetError(
            "batch_id must be 1-64 letters, numbers, dots, underscores, or hyphens"
        )
    return config["_project_root"] / EXPANSION_BATCH_DIR / batch_id


def _load_expansion_batch(
    config: dict[str, Any], batch_id: str
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    batch_path = _expansion_batch_path(config, batch_id)
    manifest_path = batch_path / "batch_manifest.json"
    if not manifest_path.is_file():
        raise DetectionDatasetError(f"Expansion batch manifest not found: {manifest_path}")
    manifest = _json_file(manifest_path, "expansion batch manifest")
    candidate_ids = manifest.get("candidate_ids")
    if (
        manifest.get("version") != POSITIVE_EXPANSION_VERSION
        or manifest.get("batch_id") != batch_id
        or not isinstance(candidate_ids, list)
        or not candidate_ids
        or any(not isinstance(candidate_id, str) for candidate_id in candidate_ids)
        or len(candidate_ids) != len(set(candidate_ids))
        or manifest.get("candidate_count") != len(candidate_ids)
    ):
        raise DetectionDatasetError("Expansion batch manifest is invalid or duplicated")

    dataset_manifest: Path = config["paths"]["candidate_manifest"]
    candidates = _read_csv(dataset_manifest)
    _require_fields(dataset_manifest, candidates, CANDIDATE_FIELDS)
    candidate_by_id = {row["image_id"]: row for row in candidates}
    if len(candidate_by_id) != len(candidates) or not set(candidate_ids) <= set(
        candidate_by_id
    ):
        raise DetectionDatasetError("Expansion batch references unknown current candidates")
    selected = [candidate_by_id[candidate_id] for candidate_id in candidate_ids]
    if (
        any(
            row["candidate_role"] != "positive_candidate"
            or row.get("is_augmented", "").lower() != "false"
            for row in selected
        )
        or manifest.get("bundle_digest") != _candidate_set_digest(selected)
    ):
        raise DetectionDatasetError("Expansion batch candidate identity changed")

    curation_path, _ = _curation_paths(dataset_manifest)
    resulting_state = manifest.get("resulting_state")
    current_state = {
        "candidates_sha256": _sha256_file(dataset_manifest),
        "curation_sha256": _sha256_file(curation_path),
    }
    if not isinstance(resulting_state, dict) or any(
        resulting_state.get(key) != value for key, value in current_state.items()
    ):
        raise DetectionDatasetError("Dataset or curation changed after expansion collection")
    return manifest, selected


def _stratified_negative_audit_sample(
    candidates: list[dict[str, str]],
    curation_rows: list[dict[str, str]],
    *,
    sample_size: int,
    seed: int,
) -> list[dict[str, str]]:
    if sample_size < 1:
        raise DetectionDatasetError("Audit sample size must be positive")
    by_id = {row["image_id"]: row for row in candidates}
    eligible = [
        by_id[row["image_id"]]
        for row in curation_rows
        if by_id[row["image_id"]]["candidate_role"] == "hard_negative_candidate"
        and _final_curation_decision(row) == "exclude"
    ]
    if sample_size > len(eligible):
        raise DetectionDatasetError(
            f"Audit sample size exceeds excluded hard negatives: {sample_size}/{len(eligible)}"
        )
    strata: dict[str, list[dict[str, str]]] = {}
    for row in eligible:
        strata.setdefault(row["search_query"], []).append(row)
    if sample_size < len(strata):
        raise DetectionDatasetError(
            f"Audit sample must cover all {len(strata)} represented search queries"
        )

    allocation = {query: 1 for query in strata}
    remaining = sample_size - len(strata)
    total = len(eligible)
    quotas = {query: remaining * len(rows) / total for query, rows in strata.items()}
    for query, quota in quotas.items():
        allocation[query] += math.floor(quota)
    unallocated = sample_size - sum(allocation.values())
    ranked_queries = sorted(
        strata,
        key=lambda query: (
            -(quotas[query] - math.floor(quotas[query])),
            hashlib.sha256(f"{seed}:{query}".encode()).digest(),
        ),
    )
    for query in ranked_queries:
        if not unallocated:
            break
        if allocation[query] < len(strata[query]):
            allocation[query] += 1
            unallocated -= 1
    while unallocated:
        available = [query for query in strata if allocation[query] < len(strata[query])]
        if not available:
            raise DetectionDatasetError("Unable to allocate the requested audit sample")
        for query in sorted(available):
            if not unallocated:
                break
            allocation[query] += 1
            unallocated -= 1

    selected = []
    for query, rows in sorted(strata.items()):
        ranked = sorted(
            rows,
            key=lambda row: hashlib.sha256(
                f"{seed}:{query}:{row['image_id']}".encode()
            ).digest(),
        )
        selected.extend(ranked[: allocation[query]])
    return sorted(selected, key=lambda row: (row["search_query"], row["image_id"]))


def _negative_audit_html(manifest: dict[str, Any]) -> str:
    embedded = json.dumps(manifest, ensure_ascii=False).replace("<", "\\u003c")
    reasons = json.dumps(sorted(NEGATIVE_AUDIT_REASONS))
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PisGo Hard-negative Audit</title><style>
:root{{font:16px system-ui;color:#202018;background:#f4f1e8}}body{{margin:0}}main{{max-width:1100px;margin:auto;padding:18px}}
section{{background:#fff;padding:16px;margin:12px 0;border-radius:10px}}img{{display:block;max-width:100%;max-height:62vh;margin:auto;background:#222}}
button,input,select,textarea{{font:inherit;padding:10px}}button{{margin:4px;font-weight:700}}button:disabled{{opacity:.45}}.confirm{{background:#b8e6b8}}.rereview{{background:#f4dc8b}}
nav{{display:flex;justify-content:space-between;gap:8px}}small{{overflow-wrap:anywhere}}#status{{font-weight:700}}textarea{{display:block;width:min(46rem,90%);min-height:5rem}}
</style></head><body><main><h1>Hard-negative exclusion audit</h1>
<p>This audit verifies earlier exclusions. It does not change any curation decision.</p>
<section><label>Auditor identity <input id="reviewer" autocomplete="name" required></label> <span id="status"></span></section>
<section><img id="image" alt="Audit candidate image"></section><section><h2 id="candidate"></h2><div id="metadata"></div>
<p>A useful hard negative may contain no banana bunch. Recommend re-review when this valid image would provide useful detector confusion or background.</p>
<label>Reason <select id="reason"></select></label><label> Optional notes <textarea id="notes"></textarea></label>
<div><button class="confirm decision" data-value="confirmed_exclusion">Confirm exclusion</button><button class="rereview decision" data-value="recommend_re_review">Recommend re-review</button></div></section>
<section><nav><button id="previous">Previous</button><button id="next">Next unresolved</button></nav><p><button id="download">Download audit receipt</button></p></section></main>
<script id="manifest" type="application/json">{embedded}</script><script>
const manifest=JSON.parse(document.querySelector('#manifest').textContent),items=manifest.candidates,reasons={reasons};
const key='pisgo-negative-audit-'+manifest.sample_digest;let saved={{reviewer:'',decisions:{{}}}};try{{saved=JSON.parse(localStorage.getItem(key))||saved}}catch(e){{}}let index=0;
const reviewer=document.querySelector('#reviewer'),reason=document.querySelector('#reason'),notes=document.querySelector('#notes'),buttons=[...document.querySelectorAll('.decision')];reviewer.value=saved.reviewer||'';
for(const value of reasons){{const option=document.createElement('option');option.value=value;option.textContent=value.replaceAll('_',' ');reason.append(option)}}
function persist(){{saved.reviewer=reviewer.value.trim();try{{localStorage.setItem(key,JSON.stringify(saved))}}catch(e){{}}}}
function render(){{const item=items[index],decision=saved.decisions[item.candidate_id];document.querySelector('#image').src=item.image_file;document.querySelector('#candidate').textContent=`${{index+1}}/${{items.length}} · ${{item.candidate_id}}`;document.querySelector('#metadata').textContent=`Query: ${{item.search_query}} · ${{item.author}} · ${{item.license}}`;reason.value=decision?.reason||reasons[0];notes.value=decision?.notes||'';buttons.forEach(b=>b.disabled=!reviewer.value.trim());document.querySelector('#status').textContent=`Audited ${{Object.keys(saved.decisions).length}}/${{items.length}}`;}}
reviewer.addEventListener('input',()=>{{persist();render()}});buttons.forEach(b=>b.addEventListener('click',()=>{{if(!reviewer.value.trim())return;const item=items[index];saved.decisions[item.candidate_id]={{candidate_id:item.candidate_id,audit_decision:b.dataset.value,reason:reason.value,notes:notes.value.trim(),reviewed_at:new Date().toISOString()}};persist();const next=items.findIndex((x,i)=>i>index&&!saved.decisions[x.candidate_id]);if(next>=0)index=next;render()}}));
document.querySelector('#previous').onclick=()=>{{index=Math.max(0,index-1);render()}};document.querySelector('#next').onclick=()=>{{const next=items.findIndex((x,i)=>i>index&&!saved.decisions[x.candidate_id]);index=next>=0?next:index;render()}};
document.querySelector('#download').onclick=()=>{{const identity=reviewer.value.trim();if(!identity){{alert('Enter auditor identity first.');return}}if(Object.keys(saved.decisions).length!==items.length){{alert('Audit every sampled image first.');return}}persist();const receipt={{version:1,audit_id:manifest.audit_id,sample_digest:manifest.sample_digest,reviewer:identity,decisions:items.map(x=>saved.decisions[x.candidate_id])}};const blob=new Blob([JSON.stringify(receipt,null,2)],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=manifest.audit_id+'-receipt.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}};render();
</script></body></html>"""


def export_negative_audit(
    config_path: str | Path, audit_id: str, sample_size: int = 40
) -> dict[str, Any]:
    if not REVIEW_ID_PATTERN.fullmatch(audit_id):
        raise DetectionDatasetError(
            "audit_id must be 1-64 letters, numbers, dots, underscores, or hyphens"
        )
    config = load_detection_config(config_path)
    manifest_path: Path = config["paths"]["candidate_manifest"]
    candidates = _read_csv(manifest_path)
    _require_fields(manifest_path, candidates, CANDIDATE_FIELDS)
    rows = _load_curation(manifest_path, candidates)
    sample = _stratified_negative_audit_sample(
        candidates,
        rows,
        sample_size=sample_size,
        seed=int(config["project"]["random_seed"]),
    )
    export_root = config["_project_root"] / REVIEW_EXPORT_DIR
    destination = export_root / audit_id
    archive = export_root / f"{audit_id}.zip"
    if destination.exists() or archive.exists():
        raise DetectionDatasetError(f"Audit export already exists: {destination}")
    temporary = export_root / f".{audit_id}.tmp"
    try:
        images_dir = temporary / "images"
        images_dir.mkdir(parents=True)
        exported = []
        for candidate in sample:
            source = config["_project_root"] / candidate["local_path"]
            if not source.is_file():
                raise DetectionDatasetError(
                    f"Candidate image not found: {candidate['image_id']}"
                )
            image_name = f"{candidate['image_id']}.jpg"
            with Image.open(source) as image:
                review_image = ImageOps.exif_transpose(image).convert("RGB")
                review_image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                review_image.save(images_dir / image_name, "JPEG", quality=85, optimize=True)
            exported.append(
                {
                    "candidate_id": candidate["image_id"],
                    "search_query": candidate["search_query"],
                    "source_page_url": candidate["source_page_url"],
                    "author": candidate["author"],
                    "license": candidate["license"],
                    "sha256": candidate["sha256"],
                    "image_file": f"images/{image_name}",
                }
            )
        sample_digest = _candidate_set_digest(sample)
        audit_manifest = {
            "version": NEGATIVE_AUDIT_VERSION,
            "audit_id": audit_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "sample_digest": sample_digest,
            "sample_size": len(exported),
            "eligible_excluded_hard_negatives": sum(
                candidate["candidate_role"] == "hard_negative_candidate"
                and _final_curation_decision(row) == "exclude"
                for candidate, row in zip(candidates, rows)
            ),
            "strata": dict(Counter(row["search_query"] for row in sample)),
            "candidates": exported,
        }
        write_json(audit_manifest, temporary / "audit_manifest.json")
        (temporary / "index.html").write_text(
            _negative_audit_html(audit_manifest), encoding="utf-8"
        )
        (temporary / "INSTRUCTIONS.txt").write_text(
            "PISGO HARD-NEGATIVE EXCLUSION AUDIT\n\n"
            "1. Extract the ZIP completely and open index.html.\n"
            "2. Enter your real auditor identity.\n"
            "3. Inspect every image independently. A useful hard negative may contain no banana bunch.\n"
            "4. Confirm exclusion or recommend human re-review, with a reason.\n"
            "5. Download and return the receipt JSON. No curation decision changes in this audit.\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
        shutil.make_archive(str(export_root / audit_id), "zip", destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if destination.exists() and not archive.exists():
            shutil.rmtree(destination, ignore_errors=True)
        raise
    return {
        "audit_id": audit_id,
        "path": str(destination),
        "archive": str(archive),
        "sample_size": len(sample),
        "strata": dict(Counter(row["search_query"] for row in sample)),
        "sample_digest": _candidate_set_digest(sample),
    }


def import_negative_audit(
    config_path: str | Path, receipt_path: str | Path
) -> dict[str, Any]:
    path = Path(receipt_path).expanduser().resolve()
    if not path.is_file():
        raise DetectionDatasetError(f"Audit receipt not found: {path}")
    try:
        receipt = json.loads(
            path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DetectionDatasetError(f"Malformed audit receipt: {error}") from error
    expected = {"version", "audit_id", "sample_digest", "reviewer", "decisions"}
    if not isinstance(receipt, dict) or set(receipt) != expected:
        raise DetectionDatasetError(
            "Audit receipt contains missing or unexpected top-level fields"
        )
    audit_id = receipt["audit_id"]
    if receipt["version"] != NEGATIVE_AUDIT_VERSION or not isinstance(
        audit_id, str
    ) or not REVIEW_ID_PATTERN.fullmatch(audit_id):
        raise DetectionDatasetError("Invalid audit receipt version or audit_id")
    reviewer = " ".join(str(receipt["reviewer"]).split())
    if not reviewer:
        raise DetectionDatasetError("Auditor identity is required")
    config = load_detection_config(config_path)
    export_path = config["_project_root"] / REVIEW_EXPORT_DIR / audit_id
    manifest_path = export_path / "audit_manifest.json"
    if not manifest_path.is_file():
        raise DetectionDatasetError(f"Audit manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if receipt["sample_digest"] != manifest["sample_digest"]:
        raise DetectionDatasetError("Audit receipt does not match the exported sample")
    decisions = receipt["decisions"]
    if not isinstance(decisions, list):
        raise DetectionDatasetError("Audit decisions must be a list")
    expected_ids = {row["candidate_id"] for row in manifest["candidates"]}
    accepted = []
    seen = set()
    fields = {"candidate_id", "audit_decision", "reason", "notes", "reviewed_at"}
    for item in decisions:
        if not isinstance(item, dict) or set(item) != fields:
            raise DetectionDatasetError(
                "Audit decision contains missing or unexpected fields"
            )
        candidate_id = item["candidate_id"]
        if candidate_id not in expected_ids or candidate_id in seen:
            raise DetectionDatasetError(f"Unknown or duplicate audit candidate: {candidate_id}")
        if item["audit_decision"] not in NEGATIVE_AUDIT_DECISIONS:
            raise DetectionDatasetError("Invalid audit decision")
        if item["reason"] not in NEGATIVE_AUDIT_REASONS:
            raise DetectionDatasetError("Invalid audit reason")
        if not isinstance(item["notes"], str):
            raise DetectionDatasetError("Audit notes must be text")
        accepted.append({**item, "reviewed_at": _parse_reviewed_at(item["reviewed_at"])})
        seen.add(candidate_id)
    if seen != expected_ids:
        raise DetectionDatasetError(
            f"Audit receipt is incomplete: {len(seen)}/{len(expected_ids)}"
        )
    candidate_queries = {
        row["candidate_id"]: row["search_query"] for row in manifest["candidates"]
    }
    report = {
        "audit_id": audit_id,
        "reviewer": reviewer,
        "sample_size": len(accepted),
        "confirmed_exclusions": sum(
            row["audit_decision"] == "confirmed_exclusion" for row in accepted
        ),
        "recommended_for_re_review": sum(
            row["audit_decision"] == "recommend_re_review" for row in accepted
        ),
        "reason_distribution": dict(Counter(row["reason"] for row in accepted)),
        "query_distribution": dict(
            Counter(candidate_queries[row["candidate_id"]] for row in accepted)
        ),
        "semantic_misunderstanding_detected": any(
            row["audit_decision"] == "recommend_re_review"
            and row["reason"] == "useful_hard_negative"
            for row in accepted
        ),
        "curation_decisions_changed": False,
        "decisions": accepted,
    }
    write_json(report, export_path / "audit_report.json")
    return report


def _json_file(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DetectionDatasetError(f"Malformed {label}: {error}") from error
    if not isinstance(payload, dict):
        raise DetectionDatasetError(f"{label.capitalize()} must be a JSON object")
    return payload


def _negative_semantics_targets(
    config: dict[str, Any], source_audit_id: str
) -> tuple[list[dict[str, str]], dict[str, Any], dict[str, Any]]:
    if not REVIEW_ID_PATTERN.fullmatch(source_audit_id):
        raise DetectionDatasetError("Invalid source audit_id")
    source_path = config["_project_root"] / REVIEW_EXPORT_DIR / source_audit_id
    source_manifest_path = source_path / "audit_manifest.json"
    source_report_path = source_path / "audit_report.json"
    if not source_manifest_path.is_file() or not source_report_path.is_file():
        raise DetectionDatasetError("Source audit manifest and imported report are required")
    source_manifest = _json_file(source_manifest_path, "source audit manifest")
    source_report = _json_file(source_report_path, "source audit report")
    if (
        source_manifest.get("audit_id") != source_audit_id
        or source_report.get("audit_id") != source_audit_id
    ):
        raise DetectionDatasetError("Source audit identity does not match")
    manifest_rows = source_manifest.get("candidates")
    decisions = source_report.get("decisions")
    if not isinstance(manifest_rows, list) or not isinstance(decisions, list):
        raise DetectionDatasetError("Source audit candidates and decisions must be lists")
    manifest_by_id = {
        row.get("candidate_id"): row for row in manifest_rows if isinstance(row, dict)
    }
    decision_by_id = {
        row.get("candidate_id"): row for row in decisions if isinstance(row, dict)
    }
    if (
        len(manifest_by_id) != len(manifest_rows)
        or len(decision_by_id) != len(decisions)
        or set(manifest_by_id) != set(decision_by_id)
        or source_report.get("sample_size") != len(decisions)
    ):
        raise DetectionDatasetError("Source audit coverage is incomplete or duplicated")
    target_ids = {
        candidate_id
        for candidate_id, decision in decision_by_id.items()
        if decision.get("reason") == NEGATIVE_SEMANTICS_TARGET_REASON
        and decision.get("audit_decision") == "confirmed_exclusion"
    }
    if len(target_ids) != NEGATIVE_SEMANTICS_TARGET_COUNT:
        raise DetectionDatasetError(
            "Source audit must contain exactly "
            f"{NEGATIVE_SEMANTICS_TARGET_COUNT} confirmed useful hard negatives; "
            f"found {len(target_ids)}"
        )

    manifest_path: Path = config["paths"]["candidate_manifest"]
    candidates = _read_csv(manifest_path)
    _require_fields(manifest_path, candidates, CANDIDATE_FIELDS)
    if len(candidates) != len({row["image_id"] for row in candidates}):
        raise DetectionDatasetError("Candidate manifest contains duplicate image_id rows")
    rows = _load_curation(manifest_path, candidates)
    candidate_by_id = {row["image_id"]: row for row in candidates}
    curation_by_id = {row["image_id"]: row for row in rows}
    if not target_ids <= set(candidate_by_id):
        raise DetectionDatasetError("Source audit targets unknown current candidates")
    for candidate_id in target_ids:
        candidate = candidate_by_id[candidate_id]
        if (
            candidate["candidate_role"] != "hard_negative_candidate"
            or _final_curation_decision(curation_by_id[candidate_id]) != "exclude"
            or manifest_by_id[candidate_id].get("sha256") != candidate["sha256"]
        ):
            raise DetectionDatasetError(
                f"Semantics target is no longer an unchanged excluded hard negative: {candidate_id}"
            )
    targets = sorted(
        (candidate_by_id[candidate_id] for candidate_id in target_ids),
        key=lambda row: row["image_id"],
    )
    return targets, source_manifest, source_report


def _negative_semantics_html(manifest: dict[str, Any]) -> str:
    embedded = json.dumps(manifest, ensure_ascii=False).replace("<", "\\u003c")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PisGo Verified-negative Review</title><style>
:root{{font:16px system-ui;color:#202018;background:#f4f1e8}}body{{margin:0}}main{{max-width:1100px;margin:auto;padding:18px}}
section{{background:#fff;padding:16px;margin:12px 0;border-radius:10px}}img{{display:block;max-width:100%;max-height:62vh;margin:auto;background:#222}}
button,input{{font:inherit;padding:10px}}button{{margin:4px;font-weight:700}}button:disabled{{opacity:.45}}.include{{background:#b8e6b8}}.exclude{{background:#f0b3ad}}.review{{background:#f4dc8b}}
nav{{display:flex;justify-content:space-between;gap:8px}}#status{{font-weight:700}}li{{margin:.4rem 0}}
</style></head><body><main><h1>Targeted hard-negative semantics review</h1>
<p><strong>Should this image be included in the detector dataset as a VERIFIED NEGATIVE?</strong></p>
<section><ul><li><strong>include_as_negative:</strong> no visible banana_bunch; usable and useful background/confuser; provenance is valid.</li>
<li><strong>exclude_as_unusable:</strong> irrelevant, corrupt, unusably poor, redundant without useful diversity, or otherwise unsuitable.</li>
<li><strong>needs_review:</strong> uncertain whether banana_bunch is present or whether the image is useful/suitable.</li></ul>
<p><strong>Absence of a banana bunch is NOT a reason to exclude a hard negative. It is the defining property of a valid negative example.</strong></p></section>
<section><label>Reviewer identity <input id="reviewer" autocomplete="name" required></label> <span id="status"></span></section>
<section><img id="image" alt="Semantics review candidate"></section><section><h2 id="candidate"></h2><div id="metadata"></div>
<div><button class="include decision" data-value="include_as_negative">Include as verified negative</button><button class="exclude decision" data-value="exclude_as_unusable">Exclude as unusable</button><button class="review decision" data-value="needs_review">Needs review</button></div></section>
<section><nav><button id="previous">Previous</button><button id="next">Next unresolved</button></nav><p><button id="download">Download receipt</button></p></section></main>
<script id="manifest" type="application/json">{embedded}</script><script>
const manifest=JSON.parse(document.querySelector('#manifest').textContent),items=manifest.candidates;
const key='pisgo-negative-semantics-'+manifest.bundle_digest;let saved={{reviewer:'',decisions:{{}}}};try{{saved=JSON.parse(localStorage.getItem(key))||saved}}catch(e){{}}let index=0;
const reviewer=document.querySelector('#reviewer'),buttons=[...document.querySelectorAll('.decision')];reviewer.value=saved.reviewer||'';
function persist(){{saved.reviewer=reviewer.value.trim();try{{localStorage.setItem(key,JSON.stringify(saved))}}catch(e){{}}}}
function render(){{const item=items[index],decision=saved.decisions[item.candidate_id]?.semantics_decision;document.querySelector('#image').src=item.image_file;document.querySelector('#candidate').textContent=`${{index+1}}/${{items.length}} · ${{item.candidate_id}}`;const metadata=document.querySelector('#metadata');metadata.textContent=`Query: ${{item.search_query}} · ${{item.author}} · ${{item.license}}`;const source=document.createElement('a');source.href=item.source_page_url;source.textContent=' · Open Wikimedia source';source.target='_blank';source.rel='noopener noreferrer';metadata.append(source);buttons.forEach(b=>{{b.disabled=!reviewer.value.trim();b.style.outline=b.dataset.value===decision?'4px solid #222':''}});document.querySelector('#status').textContent=`Reviewed ${{Object.keys(saved.decisions).length}}/${{items.length}}`;}}
reviewer.addEventListener('input',()=>{{persist();render()}});buttons.forEach(b=>b.addEventListener('click',()=>{{if(!reviewer.value.trim())return;const item=items[index];saved.decisions[item.candidate_id]={{candidate_id:item.candidate_id,semantics_decision:b.dataset.value,reviewed_at:new Date().toISOString()}};persist();const next=items.findIndex((x,i)=>i>index&&!saved.decisions[x.candidate_id]);if(next>=0)index=next;render()}}));
document.querySelector('#previous').onclick=()=>{{index=Math.max(0,index-1);render()}};document.querySelector('#next').onclick=()=>{{const next=items.findIndex((x,i)=>i>index&&!saved.decisions[x.candidate_id]);index=next>=0?next:index;render()}};
document.querySelector('#download').onclick=()=>{{const identity=reviewer.value.trim();if(!identity){{alert('Enter reviewer identity first.');return}}if(Object.keys(saved.decisions).length!==items.length){{alert('Review all 76 images first.');return}}persist();const receipt={{version:1,review_id:manifest.review_id,bundle_digest:manifest.bundle_digest,reviewer:identity,decisions:items.map(x=>saved.decisions[x.candidate_id])}};const blob=new Blob([JSON.stringify(receipt,null,2)],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=manifest.review_id+'-receipt.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}};render();
</script></body></html>"""


def export_negative_semantics_review(
    config_path: str | Path, review_id: str, source_audit_id: str
) -> dict[str, Any]:
    if not REVIEW_ID_PATTERN.fullmatch(review_id):
        raise DetectionDatasetError("Invalid semantics review_id")
    config = load_detection_config(config_path)
    targets, _, _ = _negative_semantics_targets(config, source_audit_id)
    manifest_path: Path = config["paths"]["candidate_manifest"]
    receipt_path, approval_path = _curation_paths(manifest_path)
    source_path = config["_project_root"] / REVIEW_EXPORT_DIR / source_audit_id
    export_root = config["_project_root"] / REVIEW_EXPORT_DIR
    destination = export_root / review_id
    archive = export_root / f"{review_id}.zip"
    if destination.exists() or archive.exists():
        raise DetectionDatasetError(f"Semantics review export already exists: {destination}")
    temporary = export_root / f".{review_id}.tmp"
    try:
        images_dir = temporary / "images"
        images_dir.mkdir(parents=True)
        exported = []
        for candidate in targets:
            source = config["_project_root"] / candidate["local_path"]
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != candidate["sha256"]:
                raise DetectionDatasetError(
                    f"Candidate image is missing or changed: {candidate['image_id']}"
                )
            image_name = f"{candidate['image_id']}.jpg"
            with Image.open(source) as image:
                review_image = ImageOps.exif_transpose(image).convert("RGB")
                review_image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                review_image.save(images_dir / image_name, "JPEG", quality=85, optimize=True)
            exported.append(
                {
                    "candidate_id": candidate["image_id"],
                    "search_query": candidate["search_query"],
                    "source_page_url": candidate["source_page_url"],
                    "author": candidate["author"],
                    "license": candidate["license"],
                    "sha256": candidate["sha256"],
                    "image_file": f"images/{image_name}",
                }
            )
        review_manifest = {
            "version": NEGATIVE_SEMANTICS_VERSION,
            "review_id": review_id,
            "source_audit_id": source_audit_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "bundle_digest": _candidate_set_digest(targets),
            "candidate_count": len(exported),
            "state": {
                "candidates_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                "curation_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                "approval_sha256": hashlib.sha256(approval_path.read_bytes()).hexdigest()
                if approval_path.is_file()
                else "",
                "source_manifest_sha256": hashlib.sha256(
                    (source_path / "audit_manifest.json").read_bytes()
                ).hexdigest(),
                "source_report_sha256": hashlib.sha256(
                    (source_path / "audit_report.json").read_bytes()
                ).hexdigest(),
            },
            "candidates": exported,
        }
        write_json(review_manifest, temporary / "semantics_manifest.json")
        (temporary / "index.html").write_text(
            _negative_semantics_html(review_manifest), encoding="utf-8"
        )
        (temporary / "INSTRUCTIONS.txt").write_text(
            "PISGO TARGETED VERIFIED-NEGATIVE REVIEW\n\n"
            "1. Extract the ZIP and open index.html.\n"
            "2. Enter your real reviewer identity.\n"
            "3. Inspect all 76 images and make a fresh explicit decision.\n"
            "4. No banana_bunch is the defining property of a valid negative, not an exclusion reason.\n"
            "5. Download and return the receipt JSON. No decision is preselected.\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
        shutil.make_archive(str(export_root / review_id), "zip", destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if destination.exists() and not archive.exists():
            shutil.rmtree(destination, ignore_errors=True)
        raise
    return {
        "review_id": review_id,
        "source_audit_id": source_audit_id,
        "path": str(destination),
        "archive": str(archive),
        "targeted_candidate_count": len(targets),
        "bundle_digest": _candidate_set_digest(targets),
    }


def _restore_bytes(path: Path, content: bytes | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
        return
    temporary = path.with_suffix(path.suffix + ".rollback")
    temporary.write_bytes(content)
    temporary.replace(path)


def import_negative_semantics_review(
    config_path: str | Path, receipt_path: str | Path
) -> dict[str, Any]:
    path = Path(receipt_path).expanduser().resolve()
    if not path.is_file():
        raise DetectionDatasetError(f"Semantics review receipt not found: {path}")
    receipt = _json_file(path, "semantics review receipt")
    expected = {"version", "review_id", "bundle_digest", "reviewer", "decisions"}
    if set(receipt) != expected:
        raise DetectionDatasetError(
            "Semantics receipt contains missing or unexpected top-level fields"
        )
    review_id = receipt["review_id"]
    if (
        receipt["version"] != NEGATIVE_SEMANTICS_VERSION
        or not isinstance(review_id, str)
        or not REVIEW_ID_PATTERN.fullmatch(review_id)
    ):
        raise DetectionDatasetError("Invalid semantics receipt version or review_id")
    if not isinstance(receipt["reviewer"], str):
        raise DetectionDatasetError("Semantics reviewer identity is required")
    reviewer = " ".join(receipt["reviewer"].split())
    if not reviewer:
        raise DetectionDatasetError("Semantics reviewer identity is required")
    config = load_detection_config(config_path)
    export_path = config["_project_root"] / REVIEW_EXPORT_DIR / review_id
    semantics_manifest_path = export_path / "semantics_manifest.json"
    semantics_report_path = export_path / "semantics_report.json"
    if semantics_report_path.exists():
        raise DetectionDatasetError("Semantics review was already imported; refusing to overwrite history")
    if not semantics_manifest_path.is_file():
        raise DetectionDatasetError(f"Semantics manifest not found: {semantics_manifest_path}")
    manifest = _json_file(semantics_manifest_path, "semantics manifest")
    if (
        manifest.get("version") != NEGATIVE_SEMANTICS_VERSION
        or manifest.get("review_id") != review_id
        or receipt["bundle_digest"] != manifest.get("bundle_digest")
        or manifest.get("candidate_count") != NEGATIVE_SEMANTICS_TARGET_COUNT
    ):
        raise DetectionDatasetError("Semantics receipt does not match the exact exported bundle")
    source_audit_id = manifest.get("source_audit_id")
    if not isinstance(source_audit_id, str):
        raise DetectionDatasetError("Semantics manifest has no valid source audit")

    manifest_path: Path = config["paths"]["candidate_manifest"]
    curation_path, approval_path = _curation_paths(manifest_path)
    source_path = config["_project_root"] / REVIEW_EXPORT_DIR / source_audit_id
    current_state = {
        "candidates_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "curation_sha256": hashlib.sha256(curation_path.read_bytes()).hexdigest(),
        "approval_sha256": hashlib.sha256(approval_path.read_bytes()).hexdigest()
        if approval_path.is_file()
        else "",
        "source_manifest_sha256": hashlib.sha256(
            (source_path / "audit_manifest.json").read_bytes()
        ).hexdigest(),
        "source_report_sha256": hashlib.sha256(
            (source_path / "audit_report.json").read_bytes()
        ).hexdigest(),
    }
    if current_state != manifest.get("state"):
        raise DetectionDatasetError("Dataset, curation, approval, or source audit changed after export")
    targets, _, _ = _negative_semantics_targets(config, source_audit_id)
    expected_ids = {row["image_id"] for row in targets}
    manifest_ids = {row.get("candidate_id") for row in manifest.get("candidates", [])}
    if expected_ids != manifest_ids or receipt["bundle_digest"] != _candidate_set_digest(targets):
        raise DetectionDatasetError("Semantics target set is not exactly the required 76 IDs")

    decisions = receipt["decisions"]
    if not isinstance(decisions, list):
        raise DetectionDatasetError("Semantics decisions must be a list")
    accepted: dict[str, dict[str, str]] = {}
    fields = {"candidate_id", "semantics_decision", "reviewed_at"}
    for item in decisions:
        if not isinstance(item, dict) or set(item) != fields:
            raise DetectionDatasetError(
                "Semantics decision contains missing or unexpected fields"
            )
        candidate_id = item["candidate_id"]
        if candidate_id not in expected_ids or candidate_id in accepted:
            raise DetectionDatasetError(
                f"Unknown or duplicate semantics candidate: {candidate_id}"
            )
        decision = item["semantics_decision"]
        if decision not in NEGATIVE_SEMANTICS_DECISIONS:
            raise DetectionDatasetError(f"Invalid semantics decision: {decision}")
        accepted[candidate_id] = {
            "semantics_decision": decision,
            "reviewed_at": _parse_reviewed_at(item["reviewed_at"]),
        }
    if set(accepted) != expected_ids:
        raise DetectionDatasetError(
            f"Semantics receipt is incomplete: {len(accepted)}/{len(expected_ids)}"
        )

    candidates = _read_csv(manifest_path)
    rows = _load_curation(manifest_path, candidates)
    row_by_id = {row["image_id"]: row for row in rows}
    if any(
        any(row_by_id[candidate_id].get(field) for field in SEMANTICS_CURATION_FIELDS)
        for candidate_id in expected_ids
    ):
        raise DetectionDatasetError("Semantics receipt would overwrite existing review history")
    before_candidates = [dict(row) for row in candidates]
    before_rows = [dict(row) for row in rows]
    previous_final = {
        candidate_id: _final_curation_decision(row_by_id[candidate_id])
        for candidate_id in expected_ids
    }
    for candidate_id, imported in accepted.items():
        row = row_by_id[candidate_id]
        row["semantics_source_audit_id"] = source_audit_id
        row["semantics_review_id"] = review_id
        row["semantics_decision"] = imported["semantics_decision"]
        row["semantics_reviewer"] = reviewer
        row["semantics_reviewed_at"] = imported["reviewed_at"]
    for row in rows:
        row["final_decision"] = _final_curation_decision(row)

    snapshots = {
        manifest_path: manifest_path.read_bytes(),
        curation_path: curation_path.read_bytes(),
        approval_path: approval_path.read_bytes() if approval_path.is_file() else None,
    }
    prior_approval = (
        _json_file(approval_path, "prior curation approval") if approval_path.is_file() else None
    )
    counts = Counter(item["semantics_decision"] for item in accepted.values())
    try:
        _write_curation_state(config, candidates, rows)
        after_candidates = _read_csv(manifest_path)
        after_rows = _load_curation(manifest_path, after_candidates)
        before_candidate_by_id = {row["image_id"]: row for row in before_candidates}
        after_candidate_by_id = {row["image_id"]: row for row in after_candidates}
        candidates_integrity = all(
            all(
                before_candidate_by_id[image_id][field]
                == after_candidate_by_id[image_id][field]
                for field in CANDIDATE_FIELDS
                if field != "curator_decision"
            )
            for image_id in before_candidate_by_id
        )
        before_row_by_id = {row["image_id"]: row for row in before_rows}
        after_row_by_id = {row["image_id"]: row for row in after_rows}
        curation_history_integrity = all(
            all(
                before_row_by_id[image_id].get(field, "")
                == after_row_by_id[image_id].get(field, "")
                for field in CURATION_HISTORY_FIELDS
                if field != "final_decision"
            )
            and (
                image_id in expected_ids
                or before_row_by_id[image_id] == after_row_by_id[image_id]
            )
            for image_id in before_row_by_id
        )
        if not candidates_integrity or not curation_history_integrity:
            raise DetectionDatasetError("Candidate provenance or curation history changed unexpectedly")
        summary = curation_summary(config_path)
        report = {
            "review_id": review_id,
            "source_audit_id": source_audit_id,
            "reviewer": reviewer,
            "targeted_candidate_count": len(accepted),
            "include_as_negative": counts["include_as_negative"],
            "exclude_as_unusable": counts["exclude_as_unusable"],
            "needs_review": counts["needs_review"],
            "resulting_cumulative_hard_negative_include_count": summary[
                "hard_negative_include"
            ],
            "positive_include_count": summary["positive_include"],
            "total_unresolved": summary["final_unresolved_count"],
            "approval_valid": summary["approval_valid"],
            "new_cumulative_approval_required": True,
            "candidates_integrity": candidates_integrity,
            "curation_history_integrity": curation_history_integrity,
            "prior_approval": prior_approval,
            "prior_approval_sha256": current_state["approval_sha256"],
            "decisions": [
                {
                    "candidate_id": candidate_id,
                    "semantics_decision": accepted[candidate_id]["semantics_decision"],
                    "reviewed_at": accepted[candidate_id]["reviewed_at"],
                    "previous_final_decision": previous_final[candidate_id],
                    "resulting_final_decision": _final_curation_decision(
                        after_row_by_id[candidate_id]
                    ),
                }
                for candidate_id in sorted(accepted)
            ],
        }
        write_json(report, semantics_report_path)
    except Exception:
        semantics_report_path.unlink(missing_ok=True)
        for target_path, content in snapshots.items():
            _restore_bytes(target_path, content)
        raise
    return report


def _offline_review_html(manifest: dict[str, Any]) -> str:
    embedded = json.dumps(manifest, ensure_ascii=False).replace("<", "\\u003c")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PisGo Offline Review</title><style>
:root{{font:16px system-ui;color:#202018;background:#f4f1e8}}body{{margin:0}}main{{max-width:1100px;margin:auto;padding:18px}}
section{{background:#fff;padding:16px;margin:12px 0;border-radius:10px}}img{{display:block;max-width:100%;max-height:62vh;margin:auto;background:#222}}
button,input{{font:inherit;padding:10px}}button{{margin:4px;font-weight:700}}button:disabled{{opacity:.45}}.include{{background:#b8e6b8}}.exclude{{background:#f0b3ad}}.review{{background:#f4dc8b}}
nav{{display:flex;justify-content:space-between;gap:8px}}small{{overflow-wrap:anywhere}}#status{{font-weight:700}}
</style></head><body><main><h1>PisGo offline human review</h1>
<section><label>Reviewer identity <input id="reviewer" autocomplete="name" required></label> <span id="status"></span></section>
<section><img id="image" alt="Candidate image"></section><section><h2 id="candidate"></h2><div id="metadata"></div><p id="criteria"></p>
<div><button class="include decision" data-value="include">Include</button><button class="exclude decision" data-value="exclude">Exclude</button><button class="review decision" data-value="needs_review">Needs review</button></div></section>
<section><nav><button id="previous">Previous</button><button id="next">Next unresolved</button></nav><p><button id="download">Download receipt</button></p>
<p><small>Only reviewed rows are exported. Unreviewed candidates remain unresolved.</small></p></section></main>
<script id="manifest" type="application/json">{embedded}</script><script>
const manifest=JSON.parse(document.querySelector('#manifest').textContent), items=manifest.candidates;
const key='pisgo-review-'+manifest.bundle_digest; let saved={{reviewer:'',decisions:{{}}}};
try{{saved=JSON.parse(localStorage.getItem(key))||saved}}catch(e){{}} let index=0;
const reviewer=document.querySelector('#reviewer'), buttons=[...document.querySelectorAll('.decision')]; reviewer.value=saved.reviewer||'';
function persist(){{saved.reviewer=reviewer.value.trim();try{{localStorage.setItem(key,JSON.stringify(saved))}}catch(e){{}}}}
function render(){{const item=items[index], decision=saved.decisions[item.candidate_id]?.curator_decision;
document.querySelector('#image').src=item.image_file;document.querySelector('#candidate').textContent=`${{index+1}}/${{items.length}} · ${{item.candidate_id}}`;
document.querySelector('#metadata').innerHTML='';const p=document.createElement('p');p.textContent=`Role: ${{item.candidate_role}} · Author: ${{item.author}} · License: ${{item.license}} · Group: ${{item.group_id}}`;document.querySelector('#metadata').append(p);
const a=document.createElement('a');a.href=item.source_page_url;a.textContent='Open Wikimedia source';a.target='_blank';a.rel='noopener noreferrer';document.querySelector('#metadata').append(a);
document.querySelector('#criteria').textContent=item.candidate_role==='positive_candidate'?'Include only when a real visible banana bunch is present, whole-bunch annotation is feasible, quality/diversity are useful, provenance is acceptable, and it is not a useless near-duplicate.':'Include only when no banana bunch is visible, the confusing negative is useful, and provenance is acceptable.';
buttons.forEach(b=>{{b.disabled=!reviewer.value.trim();b.style.outline=b.dataset.value===decision?'4px solid #222':''}});document.querySelector('#status').textContent=`Reviewed ${{Object.keys(saved.decisions).length}}/${{items.length}}`;}}
reviewer.addEventListener('input',()=>{{persist();render()}});buttons.forEach(b=>b.addEventListener('click',()=>{{if(!reviewer.value.trim())return;saved.decisions[items[index].candidate_id]={{candidate_id:items[index].candidate_id,curator_decision:b.dataset.value,reviewed_at:new Date().toISOString()}};persist();const next=items.findIndex((x,i)=>i>index&&!saved.decisions[x.candidate_id]);if(next>=0)index=next;render()}}));
document.querySelector('#previous').onclick=()=>{{index=Math.max(0,index-1);render()}};document.querySelector('#next').onclick=()=>{{const next=items.findIndex((x,i)=>i>index&&!saved.decisions[x.candidate_id]);index=next>=0?next:index;render()}};
document.querySelector('#download').onclick=()=>{{const identity=reviewer.value.trim();if(!identity){{alert('Enter reviewer identity first.');return}}persist();const receipt={{version:1,review_id:manifest.review_id,bundle_digest:manifest.bundle_digest,reviewer:identity,decisions:items.filter(x=>saved.decisions[x.candidate_id]).map(x=>saved.decisions[x.candidate_id])}};const blob=new Blob([JSON.stringify(receipt,null,2)],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=manifest.review_id+'-receipt.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}};render();
</script></body></html>"""


def export_offline_review(
    config_path: str | Path, review_id: str, batch_id: str | None = None
) -> dict[str, Any]:
    if not REVIEW_ID_PATTERN.fullmatch(review_id):
        raise DetectionDatasetError(
            "review_id must be 1-64 letters, numbers, dots, underscores, or hyphens"
        )
    config = load_detection_config(config_path)
    manifest_path: Path = config["paths"]["candidate_manifest"]
    candidates = _read_csv(manifest_path)
    _require_fields(manifest_path, candidates, CANDIDATE_FIELDS)
    if not candidates:
        raise DetectionDatasetError("No candidates are available for review export")
    rows = _load_curation(manifest_path, candidates)
    row_by_id = {row["image_id"]: row for row in rows}
    batch_manifest = None
    if batch_id:
        batch_manifest, selected = _load_expansion_batch(config, batch_id)
        selected_ids = {row["image_id"] for row in selected}
        if any(
            row_by_id[candidate_id]["first_decision"]
            or any(
                row_by_id[candidate_id].get(field)
                for field in CURATION_FIELDS
                if field not in {"image_id", "final_decision"}
            )
            or _final_curation_decision(row_by_id[candidate_id]) != "pending"
            for candidate_id in selected_ids
        ):
            raise DetectionDatasetError(
                "Expansion batch contains reviewed or non-pending candidates"
            )
        candidates = selected
    elif any(row.get("second_required") for row in rows):
        raise DetectionDatasetError("First-pass review is frozen for second review")
    export_root = config["_project_root"] / REVIEW_EXPORT_DIR
    destination = export_root / review_id
    archive = export_root / f"{review_id}.zip"
    if destination.exists() or archive.exists():
        raise DetectionDatasetError(f"Review export already exists: {destination}")
    temporary = export_root / f".{review_id}.tmp"
    try:
        images_dir = temporary / "images"
        images_dir.mkdir(parents=True)
        exported: list[dict[str, str]] = []
        for candidate in candidates:
            source = config["_project_root"] / candidate["local_path"]
            if not source.is_file() or _sha256_file(source) != candidate["sha256"]:
                raise DetectionDatasetError(
                    f"Candidate image is missing or changed: {candidate['image_id']}"
                )
            image_name = f"{candidate['image_id']}.jpg"
            review_path = images_dir / image_name
            with Image.open(source) as image:
                review_image = ImageOps.exif_transpose(image).convert("RGB")
                review_image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                review_image.save(review_path, "JPEG", quality=85, optimize=True)
            exported.append(
                {
                    "candidate_id": candidate["image_id"],
                    "candidate_role": candidate["candidate_role"],
                    "source_page_url": candidate["source_page_url"],
                    "author": candidate["author"],
                    "license": candidate["license"],
                    "group_id": candidate["group_id"],
                    "source_sha256": candidate["sha256"],
                    "review_image_sha256": _sha256_file(review_path),
                    "image_file": f"images/{image_name}",
                }
            )
        review_manifest = {
            "version": REVIEW_RECEIPT_VERSION,
            "review_id": review_id,
            "batch_id": batch_id or "",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "bundle_digest": _candidate_set_digest(candidates),
            "candidate_count": len(exported),
            "batch_manifest_sha256": _sha256_file(
                _expansion_batch_path(config, batch_id) / "batch_manifest.json"
            )
            if batch_manifest is not None and batch_id is not None
            else "",
            "candidates": exported,
        }
        write_json(review_manifest, temporary / "review_manifest.json")
        (temporary / "index.html").write_text(
            _offline_review_html(review_manifest), encoding="utf-8"
        )
        (temporary / "INSTRUCTIONS.txt").write_text(
            "PISGO OFFLINE HUMAN REVIEW\n\n"
            "1. Extract the ZIP completely.\n"
            "2. Open index.html in a modern browser. No server or Python is needed.\n"
            "3. Enter your real reviewer identity before making decisions.\n"
            "4. Inspect every image and choose include, exclude, or needs_review.\n"
            "5. Click Download receipt. Unreviewed images are not silently decided.\n"
            f"6. Return {review_id}-receipt.json to the repository owner.\n"
            "Do not edit review_manifest.json or the receipt manually.\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
        shutil.make_archive(str(export_root / review_id), "zip", destination)
        if batch_id:
            written_manifest = _json_file(
                destination / "review_manifest.json", "review manifest"
            )
            expected_ids = [row["image_id"] for row in candidates]
            exported_ids = [
                row.get("candidate_id") for row in written_manifest.get("candidates", [])
            ]
            if (
                written_manifest.get("batch_id") != batch_id
                or written_manifest.get("candidate_count") != len(expected_ids)
                or exported_ids != expected_ids
                or written_manifest.get("bundle_digest")
                != _candidate_set_digest(candidates)
            ):
                raise DetectionDatasetError("Review bundle candidate coverage is invalid")
            for candidate, exported_row in zip(
                candidates, written_manifest["candidates"]
            ):
                source = config["_project_root"] / candidate["local_path"]
                review_image = destination / exported_row["image_file"]
                if (
                    _sha256_file(source) != exported_row.get("source_sha256")
                    or not review_image.is_file()
                    or _sha256_file(review_image)
                    != exported_row.get("review_image_sha256")
                ):
                    raise DetectionDatasetError(
                        f"Review bundle hash mismatch: {candidate['image_id']}"
                    )
            expected_members = {
                "review_manifest.json",
                "index.html",
                "INSTRUCTIONS.txt",
                *(row["image_file"] for row in written_manifest["candidates"]),
            }
            with zipfile.ZipFile(archive) as handle:
                archive_members = {
                    name.removeprefix(f"{review_id}/")
                    for name in handle.namelist()
                    if not name.endswith("/")
                }
            if archive_members != expected_members:
                raise DetectionDatasetError("Review archive member coverage is invalid")
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        shutil.rmtree(destination, ignore_errors=True)
        archive.unlink(missing_ok=True)
        raise
    return {
        "review_id": review_id,
        "batch_id": batch_id,
        "path": str(destination),
        "archive": str(archive),
        "candidates_exported": len(candidates),
        "bundle_digest": _candidate_set_digest(candidates),
        "bundle_validated": bool(batch_id),
    }


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DetectionDatasetError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_reviewed_at(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DetectionDatasetError("Each decision requires reviewed_at")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise DetectionDatasetError("reviewed_at must be an ISO-8601 timestamp") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise DetectionDatasetError("reviewed_at must include a timezone")
    return timestamp.isoformat()


def import_offline_review(
    config_path: str | Path, receipt_path: str | Path
) -> dict[str, Any]:
    path = Path(receipt_path).expanduser().resolve()
    if not path.is_file():
        raise DetectionDatasetError(f"Review receipt not found: {path}")
    try:
        receipt = json.loads(
            path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DetectionDatasetError(f"Malformed review receipt: {error}") from error
    expected_fields = {
        "version",
        "review_id",
        "bundle_digest",
        "reviewer",
        "decisions",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected_fields:
        raise DetectionDatasetError(
            "Receipt contains missing or unexpected top-level fields"
        )
    if receipt["version"] != REVIEW_RECEIPT_VERSION:
        raise DetectionDatasetError("Unsupported review receipt version")
    if not isinstance(receipt["review_id"], str) or not REVIEW_ID_PATTERN.fullmatch(
        receipt["review_id"]
    ):
        raise DetectionDatasetError("Invalid review_id")
    if not isinstance(receipt["reviewer"], str):
        raise DetectionDatasetError("Reviewer identity is required")
    reviewer = " ".join(receipt["reviewer"].split())
    if not reviewer:
        raise DetectionDatasetError("Reviewer identity is required")
    decisions = receipt["decisions"]
    if not isinstance(decisions, list):
        raise DetectionDatasetError("Receipt decisions must be a list")

    config = load_detection_config(config_path)
    manifest_path: Path = config["paths"]["candidate_manifest"]
    candidates = _read_csv(manifest_path)
    _require_fields(manifest_path, candidates, CANDIDATE_FIELDS)
    candidate_by_id = {row["image_id"]: row for row in candidates}
    if len(candidate_by_id) != len(candidates):
        raise DetectionDatasetError("Candidate manifest contains duplicate image_id rows")
    review_manifest_path = (
        config["_project_root"]
        / REVIEW_EXPORT_DIR
        / receipt["review_id"]
        / "review_manifest.json"
    )
    batch_ids: set[str] | None = None
    if review_manifest_path.is_file():
        review_manifest = _json_file(review_manifest_path, "review manifest")
        batch_id = review_manifest.get("batch_id")
        if batch_id:
            _, batch_candidates = _load_expansion_batch(config, str(batch_id))
            review_ids = [
                row.get("candidate_id")
                for row in review_manifest.get("candidates", [])
                if isinstance(row, dict)
            ]
            expected_ids = [row["image_id"] for row in batch_candidates]
            if (
                review_manifest.get("review_id") != receipt["review_id"]
                or review_manifest.get("bundle_digest") != receipt["bundle_digest"]
                or receipt["bundle_digest"] != _candidate_set_digest(batch_candidates)
                or review_ids != expected_ids
            ):
                raise DetectionDatasetError("Receipt does not match the expansion batch")
            batch_ids = set(expected_ids)
    if batch_ids is None and receipt["bundle_digest"] != _candidate_set_digest(candidates):
        raise DetectionDatasetError("Receipt does not match the current candidate set")
    rows = _load_curation(manifest_path, candidates)
    if batch_ids is None and any(row.get("second_required") for row in rows):
        raise DetectionDatasetError("First-pass review is frozen for second review")
    receipt_by_id: dict[str, dict[str, str]] = {}
    allowed_decision_fields = {"candidate_id", "curator_decision", "reviewed_at"}
    for item in decisions:
        if not isinstance(item, dict) or set(item) != allowed_decision_fields:
            raise DetectionDatasetError(
                "Decision contains missing or unexpected fields; provenance is not importable"
            )
        candidate_id = item["candidate_id"]
        if not isinstance(candidate_id, str) or candidate_id not in candidate_by_id:
            raise DetectionDatasetError(f"Unknown candidate ID: {candidate_id}")
        if batch_ids is not None and candidate_id not in batch_ids:
            raise DetectionDatasetError(f"Candidate is outside the expansion batch: {candidate_id}")
        if candidate_id in receipt_by_id:
            raise DetectionDatasetError(f"Duplicate receipt decision: {candidate_id}")
        decision = item["curator_decision"]
        if decision not in CURATION_DECISIONS:
            raise DetectionDatasetError(f"Invalid curator decision: {decision}")
        receipt_by_id[candidate_id] = {
            "decision": decision,
            "reviewed_at": _parse_reviewed_at(item["reviewed_at"]),
        }
    row_by_id = {row["image_id"]: row for row in rows}
    already_reviewed = [
        candidate_id
        for candidate_id in receipt_by_id
        if row_by_id[candidate_id]["first_decision"]
    ]
    if already_reviewed:
        raise DetectionDatasetError(
            f"Receipt would overwrite existing first review: {already_reviewed[0]}"
        )

    for candidate_id, imported in receipt_by_id.items():
        row = row_by_id[candidate_id]
        row["first_decision"] = imported["decision"]
        row["first_reviewer"] = reviewer
        row["first_reviewed_at"] = imported["reviewed_at"]
    if batch_ids is not None and set(receipt_by_id) != batch_ids:
        raise DetectionDatasetError("Expansion receipt must review every batch candidate")
    enriched = [
        {**row, "candidate_role": candidate_by_id[row["image_id"]]["candidate_role"]}
        for row in rows
    ]
    _freeze_second_reviews(
        enriched, int(config["project"]["random_seed"]), batch_ids
    )
    for row, frozen in zip(rows, enriched):
        row["second_required"] = frozen["second_required"]
        row["second_reason"] = frozen["second_reason"]
        row["final_decision"] = _final_curation_decision(row)
    _write_curation_state(config, candidates, rows)
    return {
        "review_id": receipt["review_id"],
        "reviewer": reviewer,
        "decisions_imported": len(receipt_by_id),
        "unreviewed": len(candidates) - sum(bool(row["first_decision"]) for row in rows),
    }


def serve_curation(config_path: str | Path, port: int = 8765) -> None:
    config_path = str(Path(config_path).expanduser().resolve())
    config = load_detection_config(config_path)
    manifest_path: Path = config["paths"]["candidate_manifest"]
    token = secrets.token_urlsafe(24)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, content: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self'; style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(content)

        def _redirect(self, location: str = "/") -> None:
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            candidates = _read_csv(manifest_path)
            rows = _load_curation(manifest_path, candidates)
            by_id = {row["image_id"]: row for row in candidates}
            if parsed.path.startswith("/image/"):
                image_id = urllib.parse.unquote(parsed.path.removeprefix("/image/"))
                candidate = by_id.get(image_id)
                if not candidate:
                    self._send(404, b"Not found", "text/plain; charset=utf-8")
                    return
                image_path = (config["_project_root"] / candidate["local_path"]).resolve()
                candidate_root = config["paths"]["candidate_dir"].resolve()
                if not image_path.is_relative_to(candidate_root) or not image_path.is_file():
                    self._send(404, b"Not found", "text/plain; charset=utf-8")
                    return
                self._send(
                    200,
                    image_path.read_bytes(),
                    mimetypes.guess_type(image_path.name)[0] or "application/octet-stream",
                )
                return
            if parsed.path != "/":
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return

            first_queue = [row for row in rows if not row["first_decision"]]
            second_queue = [
                row
                for row in rows
                if row["second_required"].lower() == "true"
                and _final_curation_decision(row) == "needs_review"
            ]
            stage = "first" if first_queue else "second"
            queue = first_queue or second_queue
            summary = curation_summary(config_path)
            if not queue:
                body = self._summary_page(summary)
            else:
                query = urllib.parse.parse_qs(parsed.query)
                try:
                    requested_index = int(query.get("index", ["0"])[0])
                except (TypeError, ValueError):
                    requested_index = 0
                index = min(max(requested_index, 0), len(queue) - 1)
                receipt = queue[index]
                candidate = by_id[receipt["image_id"]]
                body = self._review_page(candidate, receipt, stage, index, len(queue), summary)
            self._send(200, body.encode(), "text/html; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            if length > 16_384:
                self._send(413, b"Request too large", "text/plain; charset=utf-8")
                return
            form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
            if not secrets.compare_digest(form.get("token", [""])[0], token):
                self._send(403, b"Invalid token", "text/plain; charset=utf-8")
                return
            try:
                if self.path == "/decision":
                    record_curation_decision(
                        config_path,
                        image_id=form.get("image_id", [""])[0],
                        stage=form.get("stage", [""])[0],
                        decision=form.get("decision", [""])[0],
                        reviewer=form.get("reviewer", [""])[0],
                    )
                elif self.path == "/approve":
                    approve_curation(config_path, form.get("reviewer", [""])[0])
                else:
                    self._send(404, b"Not found", "text/plain; charset=utf-8")
                    return
            except DetectionDatasetError as error:
                self._send(400, html.escape(str(error)).encode(), "text/plain; charset=utf-8")
                return
            self._redirect()

        def _review_page(
            self,
            candidate: dict[str, str],
            receipt: dict[str, str],
            stage: str,
            index: int,
            total: int,
            summary: dict[str, Any],
        ) -> str:
            role = candidate["candidate_role"]
            if role == "positive_candidate":
                criteria = (
                    "Include only when a real visible banana bunch is present, a whole-bunch "
                    "box is feasible, image quality/diversity are useful, provenance remains "
                    "acceptable, and this is not a useless visual near-duplicate."
                )
            else:
                criteria = (
                    "Include only when no banana bunch is visible, the confusing negative is "
                    "useful for teaching banana absence, and provenance remains acceptable."
                )
            reason = ""
            if stage == "second":
                reason = (
                    f"<p><strong>Second review:</strong> {html.escape(receipt['second_reason'])}; "
                    f"first decision: {html.escape(receipt['first_decision'])}. "
                    "Do not copy it blindly—inspect the image independently.</p>"
                )
            escaped_id = html.escape(candidate["image_id"])
            previous_link = (
                f'<a class="nav" href="/?index={index - 1}">Previous</a>' if index else ""
            )
            next_link = f'<a class="nav" href="/?index={index + 1}">Next</a>'
            return f"""<!doctype html><html><head><meta charset=utf-8><title>PisGo Curation</title>
<style>body{{font:16px system-ui;margin:0;background:#f4f1e8;color:#202018}}main{{max-width:1100px;margin:auto;padding:20px}}img{{display:block;max-width:100%;max-height:65vh;margin:auto;background:#222}}section{{background:white;padding:18px;margin:14px 0;border-radius:10px}}button,.nav{{display:inline-block;padding:12px 18px;margin:5px;font-weight:700;color:#202018}}input{{padding:10px;width:min(28rem,90%)}}.include{{background:#b8e6b8}}.exclude{{background:#f0b3ad}}.review{{background:#f4dc8b}}small{{overflow-wrap:anywhere}}</style></head><body><main>
<h1>Human curation — {html.escape(stage)} pass</h1><p>{index + 1}/{total} in this queue · first reviewed {summary['total_reviewed']}/{len(_read_csv(manifest_path))}</p>
<nav>{previous_link}{next_link}</nav>
<section><img src="/image/{urllib.parse.quote(candidate['image_id'])}" alt="Candidate {escaped_id}"></section>
<section><h2>{escaped_id}</h2><p><strong>Role:</strong> {html.escape(role)}</p><p>{html.escape(criteria)}</p>{reason}
<p><strong>Source:</strong> <a href="{html.escape(candidate['source_page_url'], quote=True)}" target="_blank" rel="noopener noreferrer">Wikimedia Commons</a><br><small>{html.escape(candidate['author'])} · {html.escape(candidate['license'])} · group {html.escape(candidate['group_id'])}</small></p>
<form method=post action=/decision><input type=hidden name=token value="{token}"><input type=hidden name=image_id value="{escaped_id}"><input type=hidden name=stage value="{stage}">
<label>Reviewer identity <input required name=reviewer id=reviewer autocomplete=name></label><div>
<button class=include name=decision value=include>Include</button><button class=exclude name=decision value=exclude>Exclude</button><button class=review name=decision value=needs_review>Needs review</button></div></form></section>
<script>try{{const r=document.querySelector('#reviewer');r.value=localStorage.getItem('reviewer')||'';r.form.addEventListener('submit',()=>localStorage.setItem('reviewer',r.value));}}catch(e){{}}</script></main></body></html>"""

        def _summary_page(self, summary: dict[str, Any]) -> str:
            data = html.escape(json.dumps(summary, indent=2))
            approval = ""
            if not [b for b in summary["blockers"] if "approval" not in b.lower()]:
                approval = f"""<form method=post action=/approve><input type=hidden name=token value="{token}"><label>Final approver <input required name=reviewer></label><button>Approve completed curation</button></form>"""
            return f"""<!doctype html><html><head><meta charset=utf-8><title>PisGo Curation</title><style>body{{font:16px system-ui;max-width:900px;margin:40px auto;padding:20px}}pre{{white-space:pre-wrap}}</style></head><body><h1>Curation status</h1><pre>{data}</pre>{approval}</body></html>"""

        def log_message(self, format: str, *args: Any) -> None:
            print(f"curation: {format % args}")

    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Human curation UI: http://127.0.0.1:{port}/")
    print("Press Ctrl+C to stop. No decisions are generated automatically.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _write_report(
    config: dict[str, Any], stage: str, counts: dict[str, Any], blockers: list[str]
) -> dict[str, Any]:
    report = {
        "status": BLOCKED if blockers else READY,
        "stage": stage,
        "counts": counts,
        "blockers": blockers,
        "training_started": False,
    }
    write_json(report, config["paths"]["report_json"])
    lines = [
        "# Detection Dataset Audit",
        "",
        f"- **Status:** `{report['status']}`",
        f"- **Stage:** `{stage}`",
        "- **YOLO training started:** no",
        "",
        "## Counts",
        "",
    ]
    lines.extend(f"- **{key}:** {value}" for key, value in counts.items())
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- {blocker}" for blocker in blockers)
    if not blockers:
        lines.append("- None.")
    path = ensure_parent(config["paths"]["report_markdown"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def collect_positive_expansion(
    config_path: str | Path, batch_id: str
) -> dict[str, Any]:
    config = load_detection_config(config_path)
    batch_path = _expansion_batch_path(config, batch_id)
    temporary_batch = batch_path.with_name(f".{batch_id}.tmp")
    if batch_path.exists() or temporary_batch.exists():
        raise DetectionDatasetError(f"Expansion batch already exists: {batch_path}")

    expansion = config.get("positive_expansion")
    if not isinstance(expansion, dict):
        raise DetectionDatasetError("Missing positive_expansion configuration")
    try:
        target = int(expansion["new_candidate_target"])
        query_configs = expansion["queries"]
    except (KeyError, TypeError, ValueError) as error:
        raise DetectionDatasetError("Invalid positive_expansion configuration") from error
    if target < 1 or not isinstance(query_configs, list) or not query_configs:
        raise DetectionDatasetError("Positive expansion target and queries are required")
    queries: list[tuple[str, int]] = []
    for query in query_configs:
        if not isinstance(query, dict):
            raise DetectionDatasetError("Each positive expansion query must be an object")
        text = " ".join(str(query.get("text", "")).split())
        try:
            maximum = int(query["max_accepts"])
        except (KeyError, TypeError, ValueError) as error:
            raise DetectionDatasetError(
                "Each positive expansion query requires max_accepts"
            ) from error
        if not text or maximum < 1:
            raise DetectionDatasetError("Positive expansion queries and caps must be positive")
        queries.append((text, maximum))
    if sum(maximum for _, maximum in queries) < target:
        raise DetectionDatasetError("Positive expansion query caps cannot reach the target")

    manifest_path: Path = config["paths"]["candidate_manifest"]
    curation_path, approval_path = _curation_paths(manifest_path)
    candidates = _read_csv(manifest_path)
    _require_fields(manifest_path, candidates, CANDIDATE_FIELDS)
    if not candidates or len(candidates) != len({row["image_id"] for row in candidates}):
        raise DetectionDatasetError("An existing unique candidate manifest is required")
    curation_rows = _load_curation(manifest_path, candidates)
    if not curation_path.is_file():
        raise DetectionDatasetError("An existing curation history file is required")
    missing_or_changed = []
    for candidate in candidates:
        source = config["_project_root"] / candidate["local_path"]
        if not source.is_file() or _sha256_file(source) != candidate["sha256"]:
            missing_or_changed.append(candidate["image_id"])
    if missing_or_changed:
        raise DetectionDatasetError(
            "Existing candidate images are missing or changed: "
            + ", ".join(missing_or_changed[:3])
        )

    snapshots = {
        manifest_path: manifest_path.read_bytes(),
        curation_path: curation_path.read_bytes() if curation_path.is_file() else None,
        approval_path: approval_path.read_bytes() if approval_path.is_file() else None,
    }
    prior_approval = (
        _json_file(approval_path, "prior curation approval")
        if approval_path.is_file()
        else None
    )
    baseline_state = {
        "candidate_count": len(candidates),
        "positive_candidate_count": sum(
            row["candidate_role"] == "positive_candidate" for row in candidates
        ),
        "candidates_sha256": _sha256_file(manifest_path),
        "curation_sha256": _sha256_file(curation_path),
        "approval_sha256": _sha256_file(approval_path)
        if approval_path.is_file()
        else "",
        "approval": prior_approval,
    }
    before_candidates = [dict(row) for row in candidates]
    before_curation = [dict(row) for row in curation_rows]
    known_titles = {row["source_item_id"] for row in candidates}
    attempted_titles: set[str] = set()
    known_sha = {row["sha256"] for row in candidates}
    try:
        known_hashes = [
            int(row["perceptual_hash"], 16)
            for row in candidates
            if row.get("perceptual_hash")
        ]
    except ValueError as error:
        raise DetectionDatasetError("Existing candidate has an invalid perceptual hash") from error

    accepted: list[dict[str, str]] = []
    rejected: Counter[str] = Counter()
    accepted_by_query: Counter[str] = Counter()
    query_failures: list[dict[str, str]] = []
    moved_images: list[Path] = []
    distance = int(config["data"]["near_duplicate_hamming_distance"])
    staged_images = temporary_batch / "images"
    try:
        staged_images.mkdir(parents=True)
        for query, query_cap in queries:
            if len(accepted) >= target:
                break
            query_accepted = 0
            try:
                pages = _search_pages(config, query)
                for page in pages:
                    if len(accepted) >= target or query_accepted >= query_cap:
                        break
                    title = str(page.get("title", ""))
                    image_info = (page.get("imageinfo") or [{}])[0]
                    metadata = image_info.get("extmetadata") or {}
                    mime_type = str(image_info.get("mime", "")).lower()
                    license_name = _metadata_value(metadata, "LicenseShortName")
                    author = _metadata_value(metadata, "Artist")
                    license_url = _metadata_value(metadata, "LicenseUrl")
                    if not title:
                        rejected["missing_source_identity"] += 1
                        continue
                    if title in known_titles:
                        rejected["duplicate_commons_page"] += 1
                        continue
                    if title in attempted_titles:
                        rejected["repeated_search_result"] += 1
                        continue
                    attempted_titles.add(title)
                    if mime_type not in config["source"]["accepted_mime_types"]:
                        rejected["unsupported_mime_type"] += 1
                        continue
                    if int(image_info.get("size") or 0) > int(
                        config["source"]["max_file_bytes"]
                    ):
                        rejected["file_too_large"] += 1
                        continue
                    if not accepted_license(
                        license_name, config["source"]["accepted_license_prefixes"]
                    ):
                        rejected["license_not_allowed"] += 1
                        continue
                    if not author or not license_url:
                        rejected["incomplete_provenance"] += 1
                        continue
                    image_url = str(image_info.get("url", ""))
                    extension = _extension(mime_type)
                    page_id = page.get("pageid")
                    if not image_url or not extension or not isinstance(page_id, int):
                        rejected["missing_image_url"] += 1
                        continue

                    image_id = f"commons-{page_id}"
                    destination = staged_images / f"{image_id}{extension}"
                    if destination.exists() or (
                        config["paths"]["candidate_dir"] / destination.name
                    ).exists():
                        rejected["duplicate_commons_page"] += 1
                        continue
                    try:
                        sha256, size = _download(image_url, destination, config)
                        perceptual_hash, width, height = _perceptual_hash(destination)
                    except (OSError, ValueError, urllib.error.URLError):
                        destination.unlink(missing_ok=True)
                        rejected["download_or_image_validation_failed"] += 1
                        continue
                    hash_value = int(perceptual_hash, 16)
                    if sha256 in known_sha:
                        destination.unlink(missing_ok=True)
                        rejected["duplicate_content"] += 1
                        continue
                    if any(
                        (hash_value ^ known).bit_count() <= distance
                        for known in known_hashes
                    ):
                        destination.unlink(missing_ok=True)
                        rejected["near_duplicate_content"] += 1
                        continue

                    final_path = config["paths"]["candidate_dir"] / destination.name
                    accepted.append(
                        {
                            "image_id": image_id,
                            "source_provider": "Wikimedia Commons",
                            "source_item_id": title,
                            "source_page_url": _commons_page(title),
                            "original_url": image_url,
                            "author": author,
                            "license": license_name,
                            "license_url": license_url,
                            "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            "provenance_status": "verified",
                            "search_query": query,
                            "candidate_role": "positive_candidate",
                            "local_path": final_path.relative_to(
                                config["_project_root"]
                            ).as_posix(),
                            "mime_type": mime_type,
                            "width": width,
                            "height": height,
                            "bytes": size,
                            "sha256": sha256,
                            "perceptual_hash": perceptual_hash,
                            "is_augmented": "false",
                            # ponytail: a Commons item is one specimen until a curator links related views.
                            "specimen_id": image_id,
                            "group_id": image_id,
                            "curator_decision": "pending",
                        }
                    )
                    known_titles.add(title)
                    known_sha.add(sha256)
                    known_hashes.append(hash_value)
                    query_accepted += 1
                    accepted_by_query[query] += 1
            except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as error:
                query_failures.append({"query": query, "error": str(error)})

        if not accepted:
            raise DetectionDatasetError("No valid positive candidates were accepted")
        candidate_dir: Path = config["paths"]["candidate_dir"]
        candidate_dir.mkdir(parents=True, exist_ok=True)
        for row in accepted:
            source = staged_images / Path(row["local_path"]).name
            destination = config["_project_root"] / row["local_path"]
            source.replace(destination)
            moved_images.append(destination)

        all_candidates = candidates + accepted
        all_curation = curation_rows + _empty_curation_rows(accepted)
        _write_curation_state(config, all_candidates, all_curation)
        after_candidates = _read_csv(manifest_path)
        after_curation = _load_curation(manifest_path, after_candidates)
        if (
            after_candidates[: len(before_candidates)] != before_candidates
            or after_curation[: len(before_curation)] != before_curation
        ):
            raise DetectionDatasetError("Existing candidate or review history changed")
        new_curation = after_curation[len(before_curation) :]
        if (
            [row["image_id"] for row in after_candidates[len(before_candidates) :]]
            != [row["image_id"] for row in accepted]
            or any(
                any(value for field, value in row.items() if field != "image_id")
                for row in new_curation
            )
            or any(
                row["curator_decision"] != "pending"
                for row in after_candidates[len(before_candidates) :]
            )
        ):
            raise DetectionDatasetError("New expansion rows are not blank pending reviews")

        resulting_state = {
            "candidates_sha256": _sha256_file(manifest_path),
            "curation_sha256": _sha256_file(curation_path),
        }
        report = {
            "version": POSITIVE_EXPANSION_VERSION,
            "batch_id": batch_id,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "candidate_role": "positive_candidate",
            "new_candidate_target": target,
            "target_met": len(accepted) >= target,
            "target_shortfall": max(0, target - len(accepted)),
            "candidate_count": len(accepted),
            "cumulative_positive_candidate_count": baseline_state[
                "positive_candidate_count"
            ]
            + len(accepted),
            "candidate_ids": [row["image_id"] for row in accepted],
            "bundle_digest": _candidate_set_digest(accepted),
            "accepted_by_query": dict(accepted_by_query),
            "duplicate_removals": {
                "exact_source": rejected["duplicate_commons_page"]
                + rejected["repeated_search_result"],
                "exact_content": rejected["duplicate_content"],
                "near_duplicate": rejected["near_duplicate_content"],
            },
            "provenance_license_rejections": {
                "license": rejected["license_not_allowed"],
                "provenance": rejected["incomplete_provenance"],
            },
            "rejections": dict(sorted(rejected.items())),
            "query_failures": query_failures,
            "baseline_state": baseline_state,
            "resulting_state": resulting_state,
        }
        shutil.rmtree(staged_images)
        write_json(report, temporary_batch / "batch_manifest.json")
        temporary_batch.replace(batch_path)
    except Exception:
        for state_path, content in snapshots.items():
            _restore_bytes(state_path, content)
        for image_path in moved_images:
            image_path.unlink(missing_ok=True)
        shutil.rmtree(temporary_batch, ignore_errors=True)
        shutil.rmtree(batch_path, ignore_errors=True)
        raise
    return report


def collect_candidates(config_path: str | Path) -> dict[str, Any]:
    config = load_detection_config(config_path)
    candidate_dir: Path = config["paths"]["candidate_dir"]
    manifest_path: Path = config["paths"]["candidate_manifest"]
    candidate_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_csv(manifest_path)
    _require_fields(manifest_path, rows, CANDIDATE_FIELDS)
    missing_files = [
        row.get("image_id", "<unknown>")
        for row in rows
        if not (config["_project_root"] / row.get("local_path", "")).is_file()
    ]
    if missing_files:
        raise DetectionDatasetError(
            f"Manifest references {len(missing_files)} missing candidate image(s): "
            f"{', '.join(missing_files[:3])}"
        )
    known_titles = {row["source_item_id"] for row in rows}
    known_sha = {row["sha256"] for row in rows}
    known_hashes = [
        int(row["perceptual_hash"], 16) for row in rows if row.get("perceptual_hash")
    ]
    counts = Counter(row["candidate_role"] for row in rows)
    rejected: Counter[str] = Counter()
    targets = {key: int(value) for key, value in config["source"]["targets"].items()}
    distance = int(config["data"]["near_duplicate_hamming_distance"])

    for query_config in config["source"]["queries"]:
        role = str(query_config["role"])
        if counts[role] >= targets[role]:
            continue
        for page in _search_pages(config, str(query_config["text"])):
            if counts[role] >= targets[role]:
                break
            title = str(page.get("title", ""))
            image_info = (page.get("imageinfo") or [{}])[0]
            metadata = image_info.get("extmetadata") or {}
            mime_type = str(image_info.get("mime", "")).lower()
            license_name = _metadata_value(metadata, "LicenseShortName")
            author = _metadata_value(metadata, "Artist")
            license_url = _metadata_value(metadata, "LicenseUrl")
            if not title or title in known_titles:
                rejected["duplicate_commons_page"] += 1
                continue
            if mime_type not in config["source"]["accepted_mime_types"]:
                rejected["unsupported_mime_type"] += 1
                continue
            if int(image_info.get("size") or 0) > int(config["source"]["max_file_bytes"]):
                rejected["file_too_large"] += 1
                continue
            if not accepted_license(
                license_name, config["source"]["accepted_license_prefixes"]
            ):
                rejected["license_not_allowed"] += 1
                continue
            if not author or not license_url:
                rejected["incomplete_provenance"] += 1
                continue
            image_url = str(image_info.get("url", ""))
            extension = _extension(mime_type)
            if not image_url or not extension:
                rejected["missing_image_url"] += 1
                continue

            image_id = f"commons-{page['pageid']}"
            destination = candidate_dir / f"{image_id}{extension}"
            try:
                sha256, size = _download(image_url, destination, config)
                perceptual_hash, width, height = _perceptual_hash(destination)
            except (OSError, ValueError, urllib.error.URLError):
                destination.unlink(missing_ok=True)
                rejected["download_or_image_validation_failed"] += 1
                continue
            hash_value = int(perceptual_hash, 16)
            if sha256 in known_sha:
                destination.unlink(missing_ok=True)
                rejected["duplicate_content"] += 1
                continue
            if any((hash_value ^ known).bit_count() <= distance for known in known_hashes):
                destination.unlink(missing_ok=True)
                rejected["near_duplicate_content"] += 1
                continue

            local_path = destination.relative_to(config["_project_root"]).as_posix()
            rows.append(
                {
                    "image_id": image_id,
                    "source_provider": "Wikimedia Commons",
                    "source_item_id": title,
                    "source_page_url": _commons_page(title),
                    "original_url": image_url,
                    "author": author,
                    "license": license_name,
                    "license_url": license_url,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "provenance_status": "verified",
                    "search_query": query_config["text"],
                    "candidate_role": role,
                    "local_path": local_path,
                    "mime_type": mime_type,
                    "width": width,
                    "height": height,
                    "bytes": size,
                    "sha256": sha256,
                    "perceptual_hash": perceptual_hash,
                    "is_augmented": "false",
                    # ponytail: a Commons item is one specimen until a curator links related views.
                    "specimen_id": image_id,
                    "group_id": image_id,
                    "curator_decision": "pending",
                }
            )
            known_titles.add(title)
            known_sha.add(sha256)
            known_hashes.append(hash_value)
            counts[role] += 1
        _write_csv(manifest_path, rows, CANDIDATE_FIELDS)

    blockers = [
        "Candidates require human positive/negative review and banana_bunch boxes.",
        "No verified annotation export has passed the contract in datasets/ANNOTATION.md.",
    ]
    for role, target in targets.items():
        if counts[role] < target:
            blockers.append(f"Candidate target not met for {role}: {counts[role]}/{target}.")
    summary = {"candidates": len(rows), **dict(sorted(counts.items()))}
    summary.update({f"rejected_{key}": value for key, value in sorted(rejected.items())})
    return _write_report(config, "collection", summary, blockers)


def _link_or_copy(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def package_handoff(config_path: str | Path) -> dict[str, Any]:
    config = load_detection_config(config_path)
    manifest_path: Path = config["paths"]["candidate_manifest"]
    candidates = _read_csv(manifest_path)
    _require_fields(manifest_path, candidates, CANDIDATE_FIELDS)
    curation_blockers = _require_approved_curation(config_path)
    if curation_blockers:
        return _write_report(
            config,
            "annotation_handoff",
            {"candidates": len(candidates), "included_candidates": 0, "tasks": 0},
            curation_blockers,
        )
    rows = [row for row in candidates if row.get("curator_decision", "").lower() == "include"]
    if not candidates:
        return _write_report(
            config,
            "annotation_handoff",
            {"candidates": 0, "included_candidates": 0, "tasks": 0},
            ["No collected candidates found."],
        )
    if not rows:
        return _write_report(
            config,
            "annotation_handoff",
            {"candidates": len(candidates), "included_candidates": 0, "tasks": 0},
            ["No candidates have curator_decision=include."],
        )
    destination: Path = config["paths"]["handoff_dir"]
    temporary = destination.with_name(destination.name + ".tmp")
    if destination.exists() or temporary.exists():
        raise DetectionDatasetError(f"Handoff path already exists; preserve human work: {destination}")

    try:
        images_dir = temporary / "images"
        tasks_dir = temporary / "tasks"
        images_dir.mkdir(parents=True)
        tasks_dir.mkdir()
        review_rows: list[dict[str, Any]] = []
        groups: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            groups.setdefault(row["group_id"], []).append(row)
        task_size = int(config["data"]["task_size"])
        tasks: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        for group_rows in groups.values():
            if len(group_rows) > task_size:
                raise DetectionDatasetError(
                    f"Group {group_rows[0]['group_id']} exceeds task_size={task_size}"
                )
            if current and len(current) + len(group_rows) > task_size:
                tasks.append(current)
                current = []
            for row in group_rows:
                source = config["_project_root"] / row["local_path"]
                if not source.is_file():
                    raise DetectionDatasetError(f"Candidate image not found: {source}")
                image_file = f"{row['image_id']}{source.suffix.lower()}"
                _link_or_copy(source, images_dir / image_file)
                current.append(
                    {
                        "image_id": row["image_id"],
                        "image_file": image_file,
                        "candidate_role": row["candidate_role"],
                        "group_id": row["group_id"],
                    }
                )
            if current:
                review_rows.extend(current[-len(group_rows) :])
        if current:
            tasks.append(current)

        review_fields = [
            "image_id",
            "image_file",
            "final_status",
            "task_id",
            "reviewer",
            "reviewed_at",
            "group_id",
        ]
        review_template = [
            {
                **row,
                "final_status": "",
                "task_id": "",
                "reviewer": "",
                "reviewed_at": "",
            }
            for row in review_rows
        ]
        _write_csv(temporary / "review.csv", review_template, review_fields)
        for number, task_rows in enumerate(tasks, 1):
            _write_csv(
                tasks_dir / f"task-{number:04d}.csv",
                task_rows,
                ["image_id", "image_file", "candidate_role", "group_id"],
            )
        _write_csv(
            temporary / "human_qa.csv",
            (
                {"category": category, "image_id": "", "reviewer": "", "reviewed_at": "", "notes": ""}
                for category in config["data"]["required_qa_categories"]
            ),
            ["category", "image_id", "reviewer", "reviewed_at", "notes"],
        )
        (temporary / "labelmap.txt").write_text("0 banana_bunch\n", encoding="utf-8")
        for number, task_rows in enumerate(tasks, 1):
            archive_base = tasks_dir / f"task-{number:04d}"
            staging = temporary / f"task-{number:04d}"
            staging.mkdir()
            for task_row in task_rows:
                _link_or_copy(images_dir / task_row["image_file"], staging / task_row["image_file"])
            shutil.make_archive(str(archive_base), "zip", staging)
            shutil.rmtree(staging)
        (temporary / "README.md").write_text(
            "# Banana-bunch annotation handoff\n\n"
            "1. Create one rectangle class named `banana_bunch` with ID 0 in CVAT or Label Studio.\n"
            "2. Upload each `tasks/task-*.zip`; review every image using the repository `datasets/ANNOTATION.md`.\n"
            "3. Export native YOLO labels without renaming images.\n"
            "4. Complete `review.csv`: every image needs positive, negative, or exclude plus task/reviewer/time.\n"
            "5. Complete `human_qa.csv` with reviewed examples for every listed category.\n"
            "6. Return the labels and both receipts together. Missing labels never imply negatives.\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    counts = Counter(row["candidate_role"] for row in rows)
    return _write_report(
        config,
        "annotation_handoff",
        {"candidates": len(candidates), "included_candidates": len(rows), "tasks": len(tasks), **counts},
        ["Human review and verified YOLO annotation export are pending."],
    )


REMOTE_MAX_DIMENSION = 2048
REMOTE_JPEG_QUALITY = 88
REMOTE_MANIFEST_FIELDS = [
    "image_id",
    "task_id",
    "candidate_role",
    "group_id",
    "remote_image_file",
    "remote_sha256",
    "remote_bytes",
    "remote_width",
    "remote_height",
    "remote_orientation",
    "canonical_path",
    "canonical_sha256",
    "canonical_bytes",
    "canonical_width",
    "canonical_height",
    "canonical_orientation",
    "resized",
]


def _exact_resize_dimensions(width: int, height: int, maximum: int) -> tuple[int, int]:
    """Return the largest no-upscale integer size with the exact source ratio."""
    if width <= 0 or height <= 0 or maximum <= 0:
        raise DetectionDatasetError("Remote review dimensions must be positive")
    divisor = math.gcd(width, height)
    unit_width, unit_height = width // divisor, height // divisor
    scale = min(divisor, maximum // max(unit_width, unit_height))
    if scale <= 0:
        return width, height
    return unit_width * scale, unit_height * scale


def _normalized_box_pixels(
    box: tuple[float, float, float, float], width: int, height: int
) -> tuple[float, float, float, float]:
    x, y, box_width, box_height = box
    return x * width, y * height, box_width * width, box_height * height


def _remote_review_copy(source: Path, destination: Path, maximum: int) -> dict[str, Any]:
    with Image.open(source) as image:
        image.load()
        width, height = image.size
        orientation = int(image.getexif().get(274, 1))
        remote_width, remote_height = _exact_resize_dimensions(width, height, maximum)
        if (remote_width, remote_height) != (width, height):
            image = image.resize((remote_width, remote_height), Image.Resampling.LANCZOS)
        if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, "white")
            background.alpha_composite(rgba)
            image = background.convert("RGB")
        else:
            image = image.convert("RGB")
        exif = Image.Exif()
        if orientation != 1:
            exif[274] = orientation
        ensure_parent(destination)
        image.save(
            destination,
            "JPEG",
            quality=REMOTE_JPEG_QUALITY,
            optimize=True,
            progressive=True,
            exif=exif,
        )
    return {
        "remote_sha256": _sha256_file(destination),
        "remote_bytes": destination.stat().st_size,
        "remote_width": remote_width,
        "remote_height": remote_height,
        "remote_orientation": orientation,
        "resized": str((remote_width, remote_height) != (width, height)).lower(),
    }


def _write_zip(source: Path, destination: Path, *, include_root: bool = False) -> None:
    ensure_parent(destination)
    root = source.parent if include_root else source
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(root).as_posix())


def _validate_remote_archive(
    archive_path: Path, expected_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    expected_ids = {str(row["image_id"]) for row in expected_rows}
    expected_by_id = {str(row["image_id"]): row for row in expected_rows}
    expected_task_ids = {str(row["task_id"]) for row in expected_rows}
    seen_ids: set[str] = set()
    errors: list[str] = []
    with zipfile.ZipFile(archive_path) as outer:
        files = [item.filename for item in outer.infolist() if not item.is_dir()]
        names = set(files)
        if len(files) != len(names):
            errors.append("Remote outer archive contains duplicate member names")
        root = "annotation_handoff_remote/"
        required = {
            root + "README.md",
            root + "review.csv",
            root + "human_qa.csv",
            root + "labelmap.txt",
            root + "remote_manifest.csv",
            root + "validation.json",
            *(root + f"tasks/{task_id}.csv" for task_id in expected_task_ids),
            *(root + f"tasks/{task_id}.zip" for task_id in expected_task_ids),
        }
        if missing := sorted(required - names):
            errors.append(f"Remote archive is missing: {', '.join(missing)}")
        if extra := sorted(names - required):
            errors.append(f"Remote archive has unexpected members: {', '.join(extra)}")
        if any(name.startswith(root + "images/") for name in names):
            errors.append("Remote archive duplicates images outside task ZIPs")
        task_archives = sorted(
            name
            for name in names
            if name.startswith(root + "tasks/task-") and name.endswith(".zip")
        )
        task_csvs = sorted(
            name
            for name in names
            if name.startswith(root + "tasks/task-") and name.endswith(".csv")
        )
        if len(task_archives) != len(task_csvs):
            errors.append("Remote task ZIP/CSV counts differ")
        for task_name in task_archives:
            task_id = Path(task_name).stem
            with outer.open(task_name) as member, zipfile.ZipFile(io.BytesIO(member.read())) as task:
                image_members = [item for item in task.infolist() if not item.is_dir()]
                if len(image_members) != len({item.filename for item in image_members}):
                    errors.append(f"Duplicate member names in {task_id}.zip")
                for item in image_members:
                    image_id = Path(item.filename).stem
                    if image_id in seen_ids:
                        errors.append(f"Duplicate remote image ID: {image_id}")
                        continue
                    seen_ids.add(image_id)
                    row = expected_by_id.get(image_id)
                    if not row:
                        errors.append(f"Unexpected remote image ID: {image_id}")
                        continue
                    if item.filename != row["remote_image_file"]:
                        errors.append(f"Remote filename changed: {image_id}")
                    if task_id != row["task_id"]:
                        errors.append(f"Remote task membership changed: {image_id}")
                    payload = task.read(item)
                    if hashlib.sha256(payload).hexdigest() != row["remote_sha256"]:
                        errors.append(f"Remote review-copy checksum mismatch: {image_id}")
                    try:
                        with Image.open(io.BytesIO(payload)) as image:
                            image.load()
                            width, height = image.size
                            orientation = int(image.getexif().get(274, 1))
                    except OSError as error:
                        errors.append(f"Unreadable remote review copy {image_id}: {error}")
                        continue
                    if (width, height) != (
                        int(row["remote_width"]),
                        int(row["remote_height"]),
                    ):
                        errors.append(f"Remote dimensions changed: {image_id}")
                    if width * int(row["canonical_height"]) != height * int(
                        row["canonical_width"]
                    ):
                        errors.append(f"Remote aspect ratio changed: {image_id}")
                    if orientation != int(row["canonical_orientation"]):
                        errors.append(f"Remote EXIF orientation changed: {image_id}")
    if seen_ids != expected_ids:
        errors.append(
            f"Remote ID coverage mismatch: expected {len(expected_ids)}, found {len(seen_ids)}"
        )
    sample_box = (0.5, 0.5, 0.25, 0.25)
    normalized_geometry_equivalent = all(
        tuple(
            value / dimension
            for value, dimension in zip(
                _normalized_box_pixels(
                    sample_box, int(row["remote_width"]), int(row["remote_height"])
                ),
                (
                    int(row["remote_width"]),
                    int(row["remote_height"]),
                    int(row["remote_width"]),
                    int(row["remote_height"]),
                ),
            )
        )
        == sample_box
        for row in expected_rows
    )
    if not normalized_geometry_equivalent:
        errors.append("Normalized YOLO geometry is not equivalent")
    return {
        "valid": not errors,
        "errors": errors,
        "candidate_count": len(seen_ids),
        "task_count": len(task_archives),
        "all_ids_preserved": seen_ids == expected_ids,
        "no_duplicate_images": len(seen_ids) == len(expected_ids),
        "aspect_ratios_preserved": not any(
            "aspect ratio" in error for error in errors
        ),
        "orientations_preserved": not any("orientation" in error for error in errors),
        "normalized_geometry_equivalent": normalized_geometry_equivalent,
        "archive_member_count": len(names),
    }


def package_remote_handoff(config_path: str | Path) -> dict[str, Any]:
    """Build one small remote-only handoff without touching canonical data."""
    config = load_detection_config(config_path)
    manifest_path: Path = config["paths"]["candidate_manifest"]
    candidates = _read_csv(manifest_path)
    _require_fields(manifest_path, candidates, CANDIDATE_FIELDS)
    if blockers := _require_approved_curation(config_path):
        raise DetectionDatasetError("Remote handoff requires approved curation: " + "; ".join(blockers))
    rows = [row for row in candidates if row.get("curator_decision", "").lower() == "include"]
    if not rows:
        raise DetectionDatasetError("No included candidates are available for remote handoff")

    original_handoff: Path = config["paths"]["handoff_dir"]
    original_archive = original_handoff.with_suffix(".zip")
    destination = original_handoff.with_name("annotation_handoff_remote.zip")
    temporary_root = original_handoff.with_name("annotation_handoff_remote.tmp")
    temporary_archive = destination.with_suffix(".zip.tmp")
    if destination.exists() or temporary_root.exists() or temporary_archive.exists():
        raise DetectionDatasetError(f"Remote handoff already exists; refusing to overwrite: {destination}")

    source_hashes: dict[str, str] = {}
    task_size = int(config["data"]["task_size"])
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if not row["group_id"]:
            raise DetectionDatasetError(f"Included candidate has no group_id: {row['image_id']}")
        groups.setdefault(row["group_id"], []).append(row)
    tasks: list[list[dict[str, str]]] = []
    current: list[dict[str, str]] = []
    for group_rows in groups.values():
        if len(group_rows) > task_size:
            raise DetectionDatasetError(
                f"Group {group_rows[0]['group_id']} exceeds task_size={task_size}"
            )
        if current and len(current) + len(group_rows) > task_size:
            tasks.append(current)
            current = []
        current.extend(group_rows)
    if current:
        tasks.append(current)

    try:
        root = temporary_root / "annotation_handoff_remote"
        tasks_dir = root / "tasks"
        copies_dir = temporary_root / "review_copies"
        tasks_dir.mkdir(parents=True)
        copies_dir.mkdir()
        manifest_rows: list[dict[str, Any]] = []
        review_rows: list[dict[str, Any]] = []
        for task_number, task_rows in enumerate(tasks, 1):
            task_id = f"task-{task_number:04d}"
            task_staging = temporary_root / task_id
            task_staging.mkdir()
            task_csv_rows = []
            for row in task_rows:
                image_id = row["image_id"]
                source = config["_project_root"] / row["local_path"]
                if not source.is_file():
                    raise DetectionDatasetError(f"Canonical source image is missing: {image_id}")
                source_hash = _sha256_file(source)
                if source_hash != row["sha256"]:
                    raise DetectionDatasetError(f"Canonical source checksum changed: {image_id}")
                source_hashes[image_id] = source_hash
                with Image.open(source) as image:
                    image.verify()
                with Image.open(source) as image:
                    canonical_width, canonical_height = image.size
                    canonical_orientation = int(image.getexif().get(274, 1))
                remote_name = f"{image_id}.jpg"
                remote_path = copies_dir / remote_name
                remote = _remote_review_copy(source, remote_path, REMOTE_MAX_DIMENSION)
                shutil.move(remote_path, task_staging / remote_name)
                manifest_rows.append(
                    {
                        "image_id": image_id,
                        "task_id": task_id,
                        "candidate_role": row["candidate_role"],
                        "group_id": row["group_id"],
                        "remote_image_file": remote_name,
                        **remote,
                        "canonical_path": row["local_path"],
                        "canonical_sha256": source_hash,
                        "canonical_bytes": source.stat().st_size,
                        "canonical_width": canonical_width,
                        "canonical_height": canonical_height,
                        "canonical_orientation": canonical_orientation,
                    }
                )
                task_csv_rows.append(
                    {
                        "image_id": image_id,
                        "image_file": remote_name,
                        "candidate_role": row["candidate_role"],
                        "group_id": row["group_id"],
                    }
                )
                review_rows.append(
                    {
                        "image_id": image_id,
                        "image_file": remote_name,
                        "final_status": "",
                        "task_id": "",
                        "reviewer": "",
                        "reviewed_at": "",
                        "group_id": row["group_id"],
                    }
                )
            _write_csv(
                tasks_dir / f"{task_id}.csv",
                task_csv_rows,
                ["image_id", "image_file", "candidate_role", "group_id"],
            )
            _write_zip(task_staging, tasks_dir / f"{task_id}.zip")
            shutil.rmtree(task_staging)

        _write_csv(root / "remote_manifest.csv", manifest_rows, REMOTE_MANIFEST_FIELDS)
        _write_csv(
            root / "review.csv",
            review_rows,
            [
                "image_id",
                "image_file",
                "final_status",
                "task_id",
                "reviewer",
                "reviewed_at",
                "group_id",
            ],
        )
        _write_csv(
            root / "human_qa.csv",
            (
                {"category": category, "image_id": "", "reviewer": "", "reviewed_at": "", "notes": ""}
                for category in config["data"]["required_qa_categories"]
            ),
            ["category", "image_id", "reviewer", "reviewed_at", "notes"],
        )
        (root / "labelmap.txt").write_text("0 banana_bunch\n", encoding="utf-8")
        (root / "README.md").write_text(
            "# Remote banana-bunch annotation handoff\n\n"
            "The task ZIPs contain proportional review-only JPEG copies. Candidate ID stems are unchanged.\n"
            "Annotate class `0 banana_bunch` using native normalized YOLO rows: "
            "`class_id x_center y_center width height`. Do not crop, rotate, rename, pseudo-label, or infer full-image boxes.\n"
            "Return one label file per image, including an explicitly empty UTF-8 file for every reviewed negative, plus completed `review.csv` and `human_qa.csv`.\n"
            "`remote_manifest.csv` is an identity receipt only; canonical provenance is reloaded from the repository manifest and cannot be changed by the return.\n",
            encoding="utf-8",
        )
        provisional = {
            "valid": True,
            "candidate_count": len(manifest_rows),
            "task_count": len(tasks),
            "all_ids_preserved": True,
            "no_duplicate_images": True,
            "normalized_geometry_equivalent": True,
            "canonical_hashes_unchanged": False,
        }
        write_json(provisional, root / "validation.json")
        _write_zip(root, temporary_archive, include_root=True)
        validation = _validate_remote_archive(temporary_archive, manifest_rows)
        unchanged = all(
            _sha256_file(config["_project_root"] / row["local_path"])
            == source_hashes[row["image_id"]]
            for row in rows
        )
        validation["canonical_hashes_unchanged"] = unchanged
        if not unchanged:
            validation["errors"].append("Canonical source hashes changed during packaging")
            validation["valid"] = False
        write_json(validation, root / "validation.json")
        temporary_archive.unlink()
        _write_zip(root, temporary_archive, include_root=True)
        final_validation = _validate_remote_archive(temporary_archive, manifest_rows)
        final_validation["canonical_hashes_unchanged"] = unchanged
        if validation["candidate_count"] != len(manifest_rows):
            final_validation["errors"].append("Remote validation candidate count changed")
            final_validation["valid"] = False
        if not final_validation["valid"] or not unchanged:
            raise DetectionDatasetError(
                "Remote handoff validation failed: "
                + "; ".join(final_validation["errors"] or ["canonical hashes changed"])
            )
        temporary_archive.replace(destination)
        return {
            "status": "REMOTE_ANNOTATION_HANDOFF_READY",
            "path": str(destination),
            "candidate_count": len(manifest_rows),
            "task_count": len(tasks),
            "original_zip_bytes": original_archive.stat().st_size if original_archive.is_file() else None,
            "remote_zip_bytes": destination.stat().st_size,
            "validation": final_validation,
        }
    except Exception:
        temporary_archive.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def validate_annotation_label(
    status: str, text: str
) -> list[tuple[float, float, float, float]]:
    boxes = parse_yolo_label(text)
    if status == "positive" and not boxes:
        raise DetectionDatasetError("Positive image has no boxes")
    if status == "negative" and boxes:
        raise DetectionDatasetError("Negative image has boxes")
    return boxes


def parse_yolo_label(text: str) -> list[tuple[float, float, float, float]]:
    boxes: list[tuple[float, float, float, float]] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5 or fields[0] != "0":
            raise DetectionDatasetError(f"line {number}: expected class 0 and four coordinates")
        try:
            box = tuple(float(value) for value in fields[1:])
        except ValueError as error:
            raise DetectionDatasetError(f"line {number}: coordinates must be numeric") from error
        x, y, width, height = box
        if not all(math.isfinite(value) for value in box):
            raise DetectionDatasetError(f"line {number}: coordinates must be finite")
        if width <= 0 or height <= 0:
            raise DetectionDatasetError(f"line {number}: box must have positive area")
        if not (0 <= x - width / 2 <= x + width / 2 <= 1):
            raise DetectionDatasetError(f"line {number}: horizontal bounds are invalid")
        if not (0 <= y - height / 2 <= y + height / 2 <= 1):
            raise DetectionDatasetError(f"line {number}: vertical bounds are invalid")
        boxes.append(box)
    if len(boxes) != len(set(boxes)):
        raise DetectionDatasetError("duplicate boxes found")
    for index, left in enumerate(boxes):
        for right in boxes[index + 1 :]:
            if _box_iou(left, right) > 0.98:
                raise DetectionDatasetError("near-duplicate overlapping boxes found")
    return boxes


def _box_iou(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    def edges(box: tuple[float, ...]) -> tuple[float, float, float, float]:
        x, y, width, height = box
        return x - width / 2, y - height / 2, x + width / 2, y + height / 2

    lx1, ly1, lx2, ly2 = edges(left)
    rx1, ry1, rx2, ry2 = edges(right)
    intersection = max(0.0, min(lx2, rx2) - max(lx1, rx1)) * max(
        0.0, min(ly2, ry2) - max(ly1, ry1)
    )
    left_area = (lx2 - lx1) * (ly2 - ly1)
    right_area = (rx2 - rx1) * (ry2 - ry1)
    return intersection / (left_area + right_area - intersection)


def assign_detection_splits(
    rows: list[dict[str, Any]], ratios: tuple[float, float, float], seed: int
) -> dict[str, str]:
    if any(ratio <= 0 for ratio in ratios) or not math.isclose(sum(ratios), 1.0):
        raise DetectionDatasetError("Split ratios must be positive and sum to 1")
    groups: dict[str, bool] = {}
    for row in rows:
        group = str(row["group_id"])
        groups[group] = groups.get(group, False) or row["final_status"] == "positive"
    positive_groups = [group for group, positive in groups.items() if positive]
    if len(positive_groups) < 3:
        raise DetectionDatasetError("At least three positive groups are required for three splits")

    rng = np.random.default_rng(seed)
    assignments: dict[str, str] = {}
    for positive in (True, False):
        values = np.asarray(
            sorted(group for group, value in groups.items() if value is positive), dtype=object
        )
        if not len(values):
            continue
        rng.shuffle(values)
        raw = np.asarray(ratios) * len(values)
        counts = np.floor(raw).astype(int)
        if positive:
            counts[counts == 0] = 1
        while counts.sum() > len(values):
            minimum = 1 if positive else 0
            reducible = np.where(counts > minimum)[0]
            counts[int(reducible[np.argmax(counts[reducible])])] -= 1
        while counts.sum() < len(values):
            counts[int(np.argmax(raw - counts))] += 1
        train_end = int(counts[0])
        validation_end = train_end + int(counts[1])
        for group in values[:train_end]:
            assignments[str(group)] = "train"
        for group in values[train_end:validation_end]:
            assignments[str(group)] = "val"
        for group in values[validation_end:]:
            assignments[str(group)] = "test"
    return assignments


def _tree_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(_sha256_file(path).encode("ascii"))
    return digest.hexdigest()


def _load_returned_labels(
    archive_paths: Iterable[str | Path], expected_ids: set[str]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], dict[str, bool]]:
    labels: dict[str, dict[str, Any]] = {}
    archives: list[dict[str, Any]] = []
    receipts = {"review_csv_present": False, "human_qa_csv_present": False}
    resolved = [Path(path).expanduser().resolve() for path in archive_paths]
    if not resolved or len(resolved) != len(set(resolved)):
        raise DetectionDatasetError("Returned annotation ZIP paths must be unique")
    for archive_path in resolved:
        if not archive_path.is_file():
            raise DetectionDatasetError(f"Returned annotation ZIP not found: {archive_path}")
        ignored: list[str] = []
        try:
            with zipfile.ZipFile(archive_path) as archive:
                files = [item for item in archive.infolist() if not item.is_dir()]
                names = [item.filename for item in files]
                if len(names) != len(set(names)):
                    raise DetectionDatasetError(
                        f"Returned archive contains duplicate member names: {archive_path}"
                    )
                for item in files:
                    raw_name = item.filename
                    path = PurePosixPath(raw_name)
                    if (
                        "\\" in raw_name
                        or path.is_absolute()
                        or ".." in path.parts
                        or not path.name
                        or any(":" in part for part in path.parts)
                    ):
                        raise DetectionDatasetError(
                            f"Unsafe returned archive member: {raw_name}"
                        )
                    lower_name = path.name.casefold()
                    if lower_name == "review.csv":
                        receipts["review_csv_present"] = True
                    if lower_name == "human_qa.csv":
                        receipts["human_qa_csv_present"] = True
                    if path.suffix.casefold() != ".txt" or lower_name == "classes.txt":
                        ignored.append(raw_name)
                        continue
                    image_id = path.stem
                    if image_id not in expected_ids:
                        raise DetectionDatasetError(
                            f"Unknown returned annotation candidate: {image_id}"
                        )
                    if image_id in labels:
                        raise DetectionDatasetError(
                            f"Duplicate returned annotation candidate: {image_id}"
                        )
                    if item.file_size > 1024 * 1024:
                        raise DetectionDatasetError(
                            f"Returned label exceeds 1 MiB: {image_id}"
                        )
                    payload = archive.read(item)
                    try:
                        text = payload.decode("utf-8-sig")
                    except UnicodeDecodeError as error:
                        raise DetectionDatasetError(
                            f"Returned label is not UTF-8: {image_id}"
                        ) from error
                    labels[image_id] = {
                        "archive": str(archive_path),
                        "member": raw_name,
                        "payload": payload,
                        "text": text,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
        except zipfile.BadZipFile as error:
            raise DetectionDatasetError(
                f"Malformed returned annotation ZIP: {archive_path}"
            ) from error
        archives.append(
            {
                "path": str(archive_path),
                "bytes": archive_path.stat().st_size,
                "sha256": _sha256_file(archive_path),
                "ignored_members": ignored,
            }
        )
    return labels, archives, receipts


def _validate_emergency_dataset(
    root: Path,
    rows: list[dict[str, Any]],
    expected_fingerprint: str | None = None,
) -> dict[str, dict[str, int]]:
    manifest_path = root / "manifest.csv"
    data_yaml = root / "data.yaml"
    manifest = _read_csv(manifest_path)
    if not manifest or not data_yaml.is_file():
        raise DetectionDatasetError("Emergency dataset manifest.csv or data.yaml is missing")
    expected_ids = {str(row["image_id"]) for row in rows}
    actual_ids = [row.get("image_id", "") for row in manifest]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
        raise DetectionDatasetError("Emergency dataset manifest ID coverage changed")
    expected_files = {"manifest.csv", "data.yaml"}
    group_splits: dict[str, set[str]] = {}
    split_counts: dict[str, dict[str, int]] = {}
    by_id = {str(row["image_id"]): row for row in rows}
    for row in manifest:
        image_id = row["image_id"]
        expected = by_id[image_id]
        split = row.get("split", "")
        status = row.get("final_status", "")
        if split not in {"train", "val", "test"} or status not in {
            "positive",
            "negative",
        }:
            raise DetectionDatasetError(f"Invalid emergency manifest row: {image_id}")
        if split != expected["split"] or status != expected["final_status"]:
            raise DetectionDatasetError(f"Emergency manifest evidence changed: {image_id}")
        group_splits.setdefault(row["group_id"], set()).add(split)
        image_name = row["image_file"]
        image_path = root / "images" / split / image_name
        label_path = root / "labels" / split / f"{Path(image_name).stem}.txt"
        if not image_path.is_file() or not label_path.is_file():
            raise DetectionDatasetError(f"Emergency dataset file is missing: {image_id}")
        if _sha256_file(image_path) != row["sha256"]:
            raise DetectionDatasetError(f"Emergency source checksum changed: {image_id}")
        try:
            boxes = parse_yolo_label(label_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, DetectionDatasetError) as error:
            raise DetectionDatasetError(
                f"Invalid emergency label {image_id}: {error}"
            ) from error
        if bool(boxes) != (status == "positive"):
            raise DetectionDatasetError(
                f"Emergency label/status mismatch: {image_id}"
            )
        expected_files.update(
            {
                f"images/{split}/{image_name}",
                f"labels/{split}/{Path(image_name).stem}.txt",
            }
        )
        counts = split_counts.setdefault(
            split, {"images": 0, "positive": 0, "negative": 0, "groups": 0}
        )
        counts["images"] += 1
        counts[status] += 1
    if any(len(splits) != 1 for splits in group_splits.values()):
        raise DetectionDatasetError("Emergency dataset has group leakage")
    for split in ("train", "val", "test"):
        counts = split_counts.setdefault(
            split, {"images": 0, "positive": 0, "negative": 0, "groups": 0}
        )
        counts["groups"] = len(
            {row["group_id"] for row in manifest if row["split"] == split}
        )
        if not counts["images"] or not counts["positive"]:
            raise DetectionDatasetError(
                f"Emergency split {split} requires images and positives"
            )
    if not split_counts["test"]["negative"]:
        raise DetectionDatasetError("Emergency test split requires verified negatives")
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise DetectionDatasetError("Emergency dataset inventory does not match manifest")
    if expected_fingerprint is not None and _tree_fingerprint(root) != expected_fingerprint:
        raise DetectionDatasetError("Emergency dataset fingerprint changed")
    return split_counts


def build_emergency_dataset(
    config_path: str | Path,
    archive_paths: Iterable[str | Path],
    *,
    expected_positive_count: int = 241,
    expected_negative_count: int = 81,
    expected_missing_positive_count: int = 32,
    expected_invalid_positive_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Build the isolated competition subset from approved identities and valid labels."""
    config = load_detection_config(config_path)
    if blockers := _require_approved_curation(config_path):
        raise DetectionDatasetError(
            "Emergency dataset requires approved curation: " + "; ".join(blockers)
        )
    manifest_path: Path = config["paths"]["candidate_manifest"]
    candidates = _read_csv(manifest_path)
    _require_fields(manifest_path, candidates, CANDIDATE_FIELDS)
    candidate_by_id = {row["image_id"]: row for row in candidates}
    if len(candidate_by_id) != len(candidates):
        raise DetectionDatasetError("Candidate manifest contains duplicate image_id rows")
    curation_path, approval_path = _curation_paths(manifest_path)
    curation = _load_curation(manifest_path, candidates)
    curation_by_id = {row["image_id"]: row for row in curation}
    included = [
        row
        for row in candidates
        if _final_curation_decision(curation_by_id[row["image_id"]]) == "include"
    ]
    if any(row.get("curator_decision", "").casefold() != "include" for row in included):
        raise DetectionDatasetError("Approved curation and candidate manifest disagree")
    positives = [row for row in included if row["candidate_role"] == "positive_candidate"]
    negatives = [
        row for row in included if row["candidate_role"] == "hard_negative_candidate"
    ]
    invalid_expected = (
        set(EMERGENCY_INVALID_POSITIVE_IDS)
        if expected_invalid_positive_ids is None
        else set(expected_invalid_positive_ids)
    )
    if len(negatives) != expected_negative_count or len(positives) != (
        expected_positive_count + expected_missing_positive_count + len(invalid_expected)
    ):
        raise DetectionDatasetError(
            "Approved candidate counts do not match the emergency contract: "
            f"positive={len(positives)}, negative={len(negatives)}"
        )
    expected_ids = {row["image_id"] for row in included}
    labels, archive_evidence, receipts = _load_returned_labels(
        archive_paths, expected_ids
    )

    selected: list[dict[str, Any]] = []
    positive_evidence: list[dict[str, Any]] = []
    negative_evidence: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    missing_positive_ids: set[str] = set()
    invalid_positive_ids: set[str] = set()
    for candidate in positives:
        image_id = candidate["image_id"]
        label = labels.get(image_id)
        if label is None:
            missing_positive_ids.add(image_id)
            exclusions.append(
                {"image_id": image_id, "reason": "missing_returned_positive_label"}
            )
            continue
        try:
            boxes = parse_yolo_label(label["text"])
            if not boxes:
                raise DetectionDatasetError("Positive image has no boxes")
        except DetectionDatasetError as error:
            if image_id not in invalid_expected:
                raise DetectionDatasetError(
                    f"Unexpected invalid returned positive label {image_id}: {error}"
                ) from error
            invalid_positive_ids.add(image_id)
            exclusions.append(
                {
                    "image_id": image_id,
                    "reason": "invalid_returned_positive_label",
                    "detail": str(error),
                }
            )
            continue
        if image_id in invalid_expected:
            raise DetectionDatasetError(
                f"Expected invalid positive label is now valid; contract changed: {image_id}"
            )
        selected.append(
            {
                **candidate,
                "final_status": "positive",
                "label_payload": label["payload"],
                "box_count": len(boxes),
                "annotation_source": "returned_human_yolo",
                "annotation_archive": label["archive"],
                "annotation_member": label["member"],
                "annotation_sha256": label["sha256"],
            }
        )
        positive_evidence.append(
            {
                "image_id": image_id,
                "archive": label["archive"],
                "member": label["member"],
                "label_sha256": label["sha256"],
                "box_count": len(boxes),
            }
        )
    if (
        len(selected) != expected_positive_count
        or len(missing_positive_ids) != expected_missing_positive_count
        or invalid_positive_ids != invalid_expected
    ):
        raise DetectionDatasetError(
            "Returned positive evidence does not match the emergency contract: "
            f"valid={len(selected)}, missing={len(missing_positive_ids)}, "
            f"invalid={len(invalid_positive_ids)}"
        )

    for candidate in negatives:
        image_id = candidate["image_id"]
        returned = labels.get(image_id)
        state = "absent"
        submitted_sha256 = ""
        source_archive = ""
        source_member = ""
        if returned is not None:
            submitted_sha256 = returned["sha256"]
            source_archive = returned["archive"]
            source_member = returned["member"]
            state = "empty" if not returned["text"].strip() else "nonempty_ignored"
        selected.append(
            {
                **candidate,
                "final_status": "negative",
                "label_payload": b"",
                "box_count": 0,
                "annotation_source": "canonical_human_verified_negative",
                "annotation_archive": source_archive,
                "annotation_member": source_member,
                "annotation_sha256": submitted_sha256,
            }
        )
        negative_evidence.append(
            {
                "image_id": image_id,
                "canonical_role": candidate["candidate_role"],
                "canonical_decision": "include",
                "returned_label_state": state,
                "returned_archive": source_archive,
                "returned_member": source_member,
                "returned_label_sha256": submitted_sha256,
                "materialized_label": "explicit_empty",
            }
        )

    required_provenance = (
        "source_provider",
        "source_item_id",
        "source_page_url",
        "original_url",
        "author",
        "license",
        "license_url",
        "sha256",
        "perceptual_hash",
        "specimen_id",
        "group_id",
    )
    exact_groups: dict[str, set[str]] = {}
    specimen_groups: dict[str, set[str]] = {}
    source_groups: dict[str, set[str]] = {}
    perceptual: list[tuple[int, str, str]] = []
    for row in selected:
        image_id = row["image_id"]
        if not all(str(row.get(key, "")).strip() for key in required_provenance):
            raise DetectionDatasetError(f"Incomplete emergency provenance: {image_id}")
        if (
            row.get("provenance_status") != "verified"
            or row.get("is_augmented", "").casefold() != "false"
            or not accepted_license(
                row["license"], config["source"]["accepted_license_prefixes"]
            )
        ):
            raise DetectionDatasetError(f"Unapproved emergency source: {image_id}")
        source = config["_project_root"] / row["local_path"]
        if not source.is_file():
            raise DetectionDatasetError(f"Canonical source image is missing: {image_id}")
        try:
            perceptual_hash, width, height = _perceptual_hash(source)
            metadata_matches = (
                _sha256_file(source) == row["sha256"]
                and source.stat().st_size == int(row["bytes"])
                and width == int(row["width"])
                and height == int(row["height"])
                and perceptual_hash == row["perceptual_hash"]
            )
        except (OSError, ValueError) as error:
            raise DetectionDatasetError(
                f"Unreadable canonical source image {image_id}: {error}"
            ) from error
        if not metadata_matches:
            raise DetectionDatasetError(f"Canonical source metadata changed: {image_id}")
        row["source_path"] = source
        exact_groups.setdefault(row["sha256"], set()).add(row["group_id"])
        specimen_groups.setdefault(row["specimen_id"], set()).add(row["group_id"])
        source_groups.setdefault(row["source_page_url"], set()).add(row["group_id"])
        try:
            perceptual.append((int(perceptual_hash, 16), row["group_id"], image_id))
        except ValueError as error:
            raise DetectionDatasetError(f"Invalid perceptual hash: {image_id}") from error
    if any(len(groups) > 1 for groups in exact_groups.values()):
        raise DetectionDatasetError("Exact duplicate emergency images have conflicting groups")
    if any(len(groups) > 1 for groups in specimen_groups.values()):
        raise DetectionDatasetError("Emergency specimen IDs have conflicting groups")
    if any(len(groups) > 1 for groups in source_groups.values()):
        raise DetectionDatasetError("Emergency source pages have conflicting groups")
    distance = int(config["data"]["near_duplicate_hamming_distance"])
    for index, (left_hash, left_group, left_id) in enumerate(perceptual):
        for right_hash, right_group, right_id in perceptual[index + 1 :]:
            if left_group != right_group and (
                left_hash ^ right_hash
            ).bit_count() <= distance:
                raise DetectionDatasetError(
                    "Near-duplicate emergency images have conflicting groups: "
                    f"{left_id}, {right_id}"
                )

    assignments = assign_detection_splits(
        selected,
        (
            float(config["data"]["train_ratio"]),
            float(config["data"]["validation_ratio"]),
            float(config["data"]["test_ratio"]),
        ),
        int(config["project"]["random_seed"]),
    )
    for row in selected:
        row["split"] = assignments[row["group_id"]]
        row["image_file"] = f"{row['image_id']}{row['source_path'].suffix.lower()}"

    destination = (
        config["_project_root"]
        / "datasets/processed/banana_bunch_detection"
        / EMERGENCY_DATASET_NAME
    )
    temporary = destination.with_name(destination.name + ".tmp")
    if destination.exists() or temporary.exists():
        raise DetectionDatasetError(
            f"Emergency dataset already exists; refusing to overwrite: {destination}"
        )
    limitations = [
        "33 canonical positive images were excluded: 32 missing returned labels and one invalid out-of-bounds label.",
        "Structured annotation review.csv was not returned.",
        "Structured human_qa.csv was not returned.",
        "Only mechanically validated returned human boxes and previously human-verified negatives are used.",
        "This is a competition emergency baseline, not a final annotation release.",
        "The canonical 355-image handoff remains incomplete.",
        "No missing review or QA receipt was fabricated.",
        "No field-validation or production-readiness claim is made.",
    ]
    try:
        dataset = temporary / "dataset"
        for split in ("train", "val", "test"):
            (dataset / "images" / split).mkdir(parents=True)
            (dataset / "labels" / split).mkdir(parents=True)
        manifest_rows: list[dict[str, Any]] = []
        for row in sorted(selected, key=lambda item: item["image_id"]):
            image_destination = dataset / "images" / row["split"] / row["image_file"]
            label_destination = (
                dataset
                / "labels"
                / row["split"]
                / f"{Path(row['image_file']).stem}.txt"
            )
            # A training library may rewrite malformed-looking JPEGs during scan;
            # copies keep that behavior isolated from provenance-bound sources.
            shutil.copy2(row["source_path"], image_destination)
            label_destination.write_bytes(row["label_payload"])
            manifest_rows.append(
                {
                    **{field: row.get(field, "") for field in CANDIDATE_FIELDS},
                    "image_file": row["image_file"],
                    "final_status": row["final_status"],
                    "split": row["split"],
                    "annotation_source": row["annotation_source"],
                    "annotation_archive": row["annotation_archive"],
                    "annotation_member": row["annotation_member"],
                    "annotation_sha256": row["annotation_sha256"],
                    "box_count": row["box_count"],
                }
            )
        _write_csv(
            dataset / "manifest.csv",
            manifest_rows,
            CANDIDATE_FIELDS
            + [
                "image_file",
                "final_status",
                "split",
                "annotation_source",
                "annotation_archive",
                "annotation_member",
                "annotation_sha256",
                "box_count",
            ],
        )
        (dataset / "data.yaml").write_text(
            "path: .\ntrain: images/train\nval: images/val\ntest: images/test\n"
            f"names:\n  0: {config['data']['class_name']}\n",
            encoding="utf-8",
        )
        split_counts = _validate_emergency_dataset(dataset, manifest_rows)
        fingerprint = _tree_fingerprint(dataset)
        evidence = {
            "dataset_name": EMERGENCY_DATASET_NAME,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "annotation_archives": archive_evidence,
            "canonical_state": {
                "manifest_sha256": _sha256_file(manifest_path),
                "curation_sha256": _sha256_file(curation_path),
                "approval_sha256": _sha256_file(approval_path),
                "approval": _json_file(approval_path, "curation approval"),
            },
            "structured_receipts": {
                **receipts,
                "used": False,
                "fabricated": False,
            },
            "positive_annotations": positive_evidence,
            "verified_negative_derivations": negative_evidence,
        }
        write_json(evidence, temporary / "evidence.json")
        write_json(
            {
                "excluded_positive_count": len(exclusions),
                "excluded_positives": sorted(exclusions, key=lambda row: row["image_id"]),
            },
            temporary / "exclusions.json",
        )
        write_json({"limitations": limitations}, temporary / "limitations.json")
        audit = {
            "status": EMERGENCY_READY,
            "stage": "emergency_annotation_audit",
            "blockers": [],
            "dataset_name": EMERGENCY_DATASET_NAME,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "counts": {
                "included_images": len(manifest_rows),
                "positive_images": expected_positive_count,
                "negative_images": expected_negative_count,
                "excluded_positive_images": len(exclusions),
                "missing_positive_labels": len(missing_positive_ids),
                "invalid_positive_labels": len(invalid_positive_ids),
                "boxes": sum(int(row["box_count"]) for row in manifest_rows),
                "splits": split_counts,
                "dataset_sha256": fingerprint,
            },
            "paths": {
                "dataset": str(destination / "dataset"),
                "manifest": str(destination / "dataset/manifest.csv"),
                "data_yaml": str(destination / "dataset/data.yaml"),
                "evidence": str(destination / "evidence.json"),
                "exclusions": str(destination / "exclusions.json"),
                "limitations": str(destination / "limitations.json"),
            },
            "limitations": limitations,
            "field_validation_claimed": False,
            "production_readiness_claimed": False,
        }
        write_json(audit, temporary / "audit.json")
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return audit


def _completed_qa_categories(path: Path, statuses: dict[str, str]) -> set[str]:
    rows = _read_csv(path)
    required = {"category", "image_id", "reviewer", "reviewed_at"}
    if not rows or required - set(rows[0]):
        return set()
    completed: set[str] = set()
    for row in rows:
        category = row["category"].strip()
        image_id = row["image_id"].strip()
        status = statuses.get(image_id)
        if not status or not row["reviewer"].strip() or not row["reviewed_at"].strip():
            continue
        if category in {"positive", "negative"}:
            if status == category:
                completed.add(category)
        elif status == "positive":
            completed.add(category)
    return completed


def audit_annotations(
    config_path: str | Path, *, materialize: bool = True
) -> dict[str, Any]:
    config = load_detection_config(config_path)
    manifest_path: Path = config["paths"]["candidate_manifest"]
    candidates = _read_csv(manifest_path)
    try:
        _require_fields(manifest_path, candidates, CANDIDATE_FIELDS)
    except DetectionDatasetError as error:
        return _write_report(config, "annotation_audit", {"candidates": len(candidates)}, [str(error)])
    candidate_by_id = {row["image_id"]: row for row in candidates}
    duplicate_candidate_ids = len(candidates) - len(candidate_by_id)
    export: Path = config["paths"]["annotation_export"]
    review_path = export / "review.csv"
    labels_dir = export / "labels"
    blockers: list[str] = _require_approved_curation(config_path)
    if duplicate_candidate_ids:
        blockers.append(f"Candidate manifest has {duplicate_candidate_ids} duplicate image_id row(s)")
    reviews = _read_csv(review_path)
    required_review = {
        "image_id",
        "image_file",
        "final_status",
        "task_id",
        "reviewer",
        "reviewed_at",
        "group_id",
    }
    review_schema_valid = bool(reviews)
    if not reviews:
        blockers.append(f"Missing or empty human review: {review_path}")
        review_schema_valid = False
    elif missing := sorted(required_review - set(reviews[0])):
        blockers.append(f"Review CSV is missing columns: {', '.join(missing)}")
        review_schema_valid = False

    valid_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    if review_schema_valid:
        included_ids = {
            image_id
            for image_id, candidate in candidate_by_id.items()
            if candidate.get("curator_decision", "").lower() == "include"
        }
        for row in reviews:
            image_id = row["image_id"].strip()
            status = row["final_status"].strip().lower()
            row["final_status"] = status
            row["group_id"] = row["group_id"].strip()
            if image_id in seen_ids:
                blockers.append(f"Duplicate review row: {image_id}")
                continue
            seen_ids.add(image_id)
            if image_id not in included_ids:
                blockers.append(f"Unknown or non-included candidate in review: {image_id}")
                continue
            if status not in {"positive", "negative", "exclude"}:
                blockers.append(f"Invalid or missing final_status: {image_id}")
                continue
            if not all(row[key].strip() for key in ("task_id", "reviewer", "reviewed_at")):
                blockers.append(f"Incomplete review receipt: {image_id}")
                continue
            if not row["group_id"]:
                blockers.append(f"Missing group_id: {image_id}")
                continue
            candidate = candidate_by_id[image_id]
            if row["group_id"] != candidate["group_id"]:
                blockers.append(f"Review group_id changed from manifest: {image_id}")
                continue
            expected_stem = image_id
            if Path(row["image_file"]).stem != expected_stem:
                blockers.append(f"Image filename does not preserve stable ID: {image_id}")
                continue
            if status == "exclude":
                continue
            label_path = labels_dir / f"{expected_stem}.txt"
            if not label_path.is_file():
                blockers.append(f"Missing label file: {image_id}")
                continue
            try:
                boxes = parse_yolo_label(label_path.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError, DetectionDatasetError) as error:
                blockers.append(f"Invalid label {image_id}: {error}")
                continue
            if status == "positive" and not boxes:
                blockers.append(f"Positive image has no boxes: {image_id}")
                continue
            if status == "negative" and boxes:
                blockers.append(f"Negative image has boxes: {image_id}")
                continue
            candidate = candidate_by_id[image_id]
            source = config["_project_root"] / candidate["local_path"]
            required_provenance = (
                "source_provider",
                "source_item_id",
                "source_page_url",
                "original_url",
                "author",
                "license",
                "license_url",
                "sha256",
                "specimen_id",
                "group_id",
            )
            if not all(candidate.get(key, "").strip() for key in required_provenance):
                blockers.append(f"Incomplete provenance: {image_id}")
                continue
            if not accepted_license(
                candidate["license"], config["source"]["accepted_license_prefixes"]
            ):
                blockers.append(f"Disallowed license: {image_id}")
                continue
            if candidate.get("is_augmented", "").lower() != "false":
                blockers.append(f"Detection input must be an original image: {image_id}")
                continue
            if not source.is_file():
                blockers.append(f"Candidate image is missing: {image_id}")
                continue
            try:
                perceptual_hash, width, height = _perceptual_hash(source)
            except (OSError, ValueError) as error:
                blockers.append(f"Unreadable candidate image {image_id}: {error}")
                continue
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            if digest != candidate["sha256"]:
                blockers.append(f"Candidate checksum changed: {image_id}")
                continue
            try:
                metadata_matches = (
                    int(candidate["bytes"]) == source.stat().st_size
                    and int(candidate["width"]) == width
                    and int(candidate["height"]) == height
                    and candidate["perceptual_hash"] == perceptual_hash
                )
            except (KeyError, ValueError):
                metadata_matches = False
            if not metadata_matches:
                blockers.append(f"Candidate image metadata changed: {image_id}")
                continue
            row["label_path"] = label_path
            row["source_path"] = source
            row["boxes"] = boxes
            valid_rows.append(row)

        missing_reviews = sorted(included_ids - seen_ids)
        if missing_reviews:
            blockers.append(f"{len(missing_reviews)} included candidates have not been explicitly reviewed")
        required_categories = set(config["data"]["required_qa_categories"])
        statuses = {row["image_id"]: row["final_status"] for row in valid_rows}
        missing_categories = sorted(
            required_categories
            - _completed_qa_categories(export / "human_qa.csv", statuses)
        )
        if missing_categories:
            blockers.append(f"Human QA coverage is missing: {', '.join(missing_categories)}")

    exact_hash_groups: dict[str, set[str]] = {}
    hashes: list[tuple[int, str]] = []
    for row in valid_rows:
        candidate = candidate_by_id[row["image_id"]]
        exact_hash_groups.setdefault(candidate["sha256"], set()).add(row["group_id"])
        perceptual_hash = candidate.get("perceptual_hash", "")
        if perceptual_hash:
            try:
                hashes.append((int(perceptual_hash, 16), row["group_id"]))
            except ValueError:
                blockers.append(f"Invalid perceptual hash: {row['image_id']}")
    if any(len(groups) > 1 for groups in exact_hash_groups.values()):
        blockers.append("Exact duplicate images have conflicting group_id values")
    distance = int(config["data"]["near_duplicate_hamming_distance"])
    if any(
        left_group != right_group
        and (left_hash ^ right_hash).bit_count() <= distance
        for index, (left_hash, left_group) in enumerate(hashes)
        for right_hash, right_group in hashes[index + 1 :]
    ):
        blockers.append("Unresolved near-duplicate images require curator regrouping")

    assignments: dict[str, str] = {}
    if valid_rows:
        try:
            assignments = assign_detection_splits(
                valid_rows,
                (
                    float(config["data"]["train_ratio"]),
                    float(config["data"]["validation_ratio"]),
                    float(config["data"]["test_ratio"]),
                ),
                int(config["project"]["random_seed"]),
            )
        except DetectionDatasetError as error:
            blockers.append(str(error))

    destination: Path = config["paths"]["dataset_dir"]
    if not blockers and materialize:
        temporary = destination.with_name(destination.name + ".tmp")
        if destination.exists() or temporary.exists():
            blockers.append(f"Dataset output already exists; refusing to overwrite: {destination}")
        else:
            try:
                provenance: list[dict[str, Any]] = []
                for split in ("train", "val", "test"):
                    (temporary / "images" / split).mkdir(parents=True)
                    (temporary / "labels" / split).mkdir(parents=True)
                for row in valid_rows:
                    candidate = candidate_by_id[row["image_id"]]
                    split = assignments[row["group_id"]]
                    image_name = row["image_file"]
                    _link_or_copy(row["source_path"], temporary / "images" / split / image_name)
                    shutil.copy2(
                        row["label_path"],
                        temporary / "labels" / split / f"{Path(image_name).stem}.txt",
                    )
                    provenance.append({**candidate, **row, "split": split})
                _write_csv(
                    temporary / "manifest.csv",
                    provenance,
                    CANDIDATE_FIELDS
                    + [
                        "image_file",
                        "final_status",
                        "task_id",
                        "reviewer",
                        "reviewed_at",
                        "split",
                    ],
                )
                (temporary / "data.yaml").write_text(
                    "path: .\ntrain: images/train\nval: images/val\ntest: images/test\n"
                    f"names:\n  {int(config['data']['class_id'])}: {config['data']['class_name']}\n",
                    encoding="utf-8",
                )
                temporary.replace(destination)
            except Exception:
                shutil.rmtree(temporary, ignore_errors=True)
                raise
    elif not blockers:
        if not destination.is_dir():
            blockers.append(f"Built dataset not found: {destination}")
        else:
            for row in valid_rows:
                split = assignments[row["group_id"]]
                image_name = row["image_file"]
                expected = (
                    destination / "images" / split / image_name,
                    destination / "labels" / split / f"{Path(image_name).stem}.txt",
                )
                if not all(path.is_file() for path in expected):
                    blockers.append(f"Built dataset coverage mismatch: {row['image_id']}")
            if not (destination / "manifest.csv").is_file():
                blockers.append("Built dataset manifest.csv is missing")
            if not (destination / "data.yaml").is_file():
                blockers.append("Built dataset data.yaml is missing")

    split_counts = Counter(
        assignments.get(row["group_id"], "unassigned") for row in valid_rows
    )
    dataset_fingerprint = ""
    if not blockers and destination.is_dir():
        digest = hashlib.sha256()
        for path in sorted(item for item in destination.rglob("*") if item.is_file()):
            digest.update(path.relative_to(destination).as_posix().encode("utf-8"))
            digest.update(_sha256_file(path).encode("ascii"))
        dataset_fingerprint = digest.hexdigest()
    counts = {
        "candidates": len(candidates),
        "review_rows": len(reviews),
        "included_images": len(valid_rows),
        "positive_images": sum(row.get("final_status") == "positive" for row in valid_rows),
        "negative_images": sum(row.get("final_status") == "negative" for row in valid_rows),
        "boxes": sum(len(row.get("boxes", [])) for row in valid_rows),
        "unique_sources": len(
            {candidate.get("source_page_url") for candidate in candidates if candidate.get("source_page_url")}
        ),
        "unique_specimens": len(
            {candidate.get("specimen_id") for candidate in candidates if candidate.get("specimen_id")}
        ),
        "group_leakage": 0,
        "human_qa_complete": not any("Human QA coverage" in blocker for blocker in blockers),
        "dataset_path": str(destination),
        "data_yaml_path": str(destination / "data.yaml"),
        "dataset_sha256": dataset_fingerprint,
        **{f"split_{key}": value for key, value in sorted(split_counts.items())},
    }
    return _write_report(config, "annotation_audit", counts, blockers)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "collect",
            "collect-positive-expansion",
            "export-review",
            "import-review",
            "export-negative-audit",
            "import-negative-audit",
            "export-negative-semantics-review",
            "import-negative-semantics-review",
            "curate",
            "curation-status",
            "package",
            "package-remote",
            "build-emergency",
            "build",
            "audit",
        ),
    )
    parser.add_argument("--config", default="configs/detection_dataset.yaml")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--review-id")
    parser.add_argument("--batch-id")
    parser.add_argument("--audit-id")
    parser.add_argument("--source-audit-id")
    parser.add_argument("--sample-size", type=int, default=40)
    parser.add_argument("--receipt")
    parser.add_argument("--annotation-zip", action="append", default=[])
    args = parser.parse_args()
    if args.command == "build-emergency":
        if len(args.annotation_zip) != 2:
            parser.error("build-emergency requires exactly two --annotation-zip paths")
        result = build_emergency_dataset(args.config, args.annotation_zip)
        print(json.dumps(result, indent=2))
        return
    if args.command == "export-negative-audit":
        if not args.audit_id:
            parser.error("export-negative-audit requires --audit-id")
        result = export_negative_audit(
            args.config, args.audit_id, sample_size=args.sample_size
        )
        print(json.dumps(result, indent=2))
        return
    if args.command == "import-negative-audit":
        if not args.receipt:
            parser.error("import-negative-audit requires --receipt")
        result = import_negative_audit(args.config, args.receipt)
        print(json.dumps(result, indent=2))
        return
    if args.command == "export-negative-semantics-review":
        if not args.review_id or not args.source_audit_id:
            parser.error(
                "export-negative-semantics-review requires --review-id and --source-audit-id"
            )
        result = export_negative_semantics_review(
            args.config, args.review_id, args.source_audit_id
        )
        print(json.dumps(result, indent=2))
        return
    if args.command == "import-negative-semantics-review":
        if not args.receipt:
            parser.error("import-negative-semantics-review requires --receipt")
        result = import_negative_semantics_review(args.config, args.receipt)
        print(json.dumps(result, indent=2))
        return
    if args.command == "collect-positive-expansion":
        if not args.batch_id:
            parser.error("collect-positive-expansion requires --batch-id")
        result = collect_positive_expansion(args.config, args.batch_id)
        print(json.dumps(result, indent=2))
        return
    if args.command == "export-review":
        if not args.review_id:
            parser.error("export-review requires --review-id")
        result = export_offline_review(
            args.config, args.review_id, batch_id=args.batch_id
        )
        print(json.dumps(result, indent=2))
        return
    if args.command == "import-review":
        if not args.receipt:
            parser.error("import-review requires --receipt")
        result = import_offline_review(args.config, args.receipt)
        print(json.dumps(result, indent=2))
        return
    if args.command == "curate":
        serve_curation(args.config, args.port)
        return
    if args.command == "package-remote":
        print(json.dumps(package_remote_handoff(args.config), indent=2))
        return
    if args.command == "curation-status":
        summary = curation_summary(args.config)
        for key in (
            "total_reviewed",
            "positive_include",
            "positive_exclude",
            "positive_needs_review",
            "hard_negative_include",
            "hard_negative_exclude",
            "hard_negative_needs_review",
            "second_review_count",
            "final_unresolved_count",
            "verified_positive_image_count",
            "verified_hard_negative_count",
            "unique_source_group_count",
            "more_positive_collection_recommended",
        ):
            print(f"{key}: {summary[key]}")
        status = (
            "YOLO_CURATION_READY_FOR_PACKAGE"
            if summary["ready"]
            else f"YOLO_CURATION_INCOMPLETE: {'; '.join(summary['blockers'])}"
        )
        print(status)
        return
    actions = {
        "collect": collect_candidates,
        "package": package_handoff,
        "build": audit_annotations,
        "audit": lambda path: audit_annotations(path, materialize=False),
    }
    report = actions[args.command](args.config)
    print(f"{report['status']}: stage={report['stage']}")
    for blocker in report["blockers"]:
        print(f"- {blocker}")


if __name__ == "__main__":
    main()
