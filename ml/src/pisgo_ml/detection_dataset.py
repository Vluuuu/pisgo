"""Collect, hand off, and audit a provenance-first banana-bunch dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
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
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import yaml
from PIL import Image, ImageOps

from .utils import ensure_parent, write_json


BLOCKED = "YOLO_DATASET_BLOCKED"
READY = "DATASET_READY_FOR_REVIEW"
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
CURATION_FIELDS = [
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
CURATION_DECISIONS = {"include", "exclude", "needs_review"}
CURATION_APPROVAL = "curation_approval.json"
CURATION_RECEIPTS = "curation.csv"
REVIEW_RECEIPT_VERSION = 1
REVIEW_EXPORT_DIR = "datasets/local_review_exports"
REVIEW_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


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
    _require_fields(receipt_path, rows, CURATION_FIELDS)
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
        return "pending"
    if row.get("second_required", "").lower() != "true":
        return first
    second = row.get("second_decision", "").strip().lower()
    if not second:
        return "needs_review"
    if row.get("second_reason") == "spot_check":
        return first if second == first else "needs_review"
    return second if second in {"include", "exclude"} else "needs_review"


def _freeze_second_reviews(rows: list[dict[str, str]], seed: int) -> None:
    if not rows or any(not row.get("first_decision") for row in rows):
        return
    if any(row.get("second_required") for row in rows):
        return
    for row in rows:
        if row["first_decision"] == "needs_review":
            row["second_required"] = "true"
            row["second_reason"] = "needs_review"
    for role in ("positive_candidate", "hard_negative_candidate"):
        included = sorted(
            (
                row
                for row in rows
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


def export_offline_review(config_path: str | Path, review_id: str) -> dict[str, Any]:
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
    if any(row.get("second_required") for row in rows):
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
            if not source.is_file():
                raise DetectionDatasetError(
                    f"Candidate image not found: {candidate['image_id']}"
                )
            image_name = f"{candidate['image_id']}.jpg"
            with Image.open(source) as image:
                review_image = ImageOps.exif_transpose(image).convert("RGB")
                review_image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                review_image.save(
                    images_dir / image_name, "JPEG", quality=85, optimize=True
                )
            exported.append(
                {
                    "candidate_id": candidate["image_id"],
                    "candidate_role": candidate["candidate_role"],
                    "source_page_url": candidate["source_page_url"],
                    "author": candidate["author"],
                    "license": candidate["license"],
                    "group_id": candidate["group_id"],
                    "image_file": f"images/{image_name}",
                }
            )
        review_manifest = {
            "version": REVIEW_RECEIPT_VERSION,
            "review_id": review_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "bundle_digest": _candidate_set_digest(candidates),
            "candidate_count": len(exported),
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
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if destination.exists() and not archive.exists():
            shutil.rmtree(destination, ignore_errors=True)
        raise
    return {
        "review_id": review_id,
        "path": str(destination),
        "archive": str(archive),
        "candidates_exported": len(candidates),
        "bundle_digest": _candidate_set_digest(candidates),
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
    if receipt["bundle_digest"] != _candidate_set_digest(candidates):
        raise DetectionDatasetError("Receipt does not match the current candidate set")
    candidate_by_id = {row["image_id"]: row for row in candidates}
    if len(candidate_by_id) != len(candidates):
        raise DetectionDatasetError("Candidate manifest contains duplicate image_id rows")
    rows = _load_curation(manifest_path, candidates)
    if any(row.get("second_required") for row in rows):
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
    enriched = [
        {**row, "candidate_role": candidate_by_id[row["image_id"]]["candidate_role"]}
        for row in rows
    ]
    _freeze_second_reviews(enriched, int(config["project"]["random_seed"]))
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
                index = min(int(query.get("index", ["0"])[0]), len(queue) - 1)
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
            return f"""<!doctype html><html><head><meta charset=utf-8><title>PisGo Curation</title>
<style>body{{font:16px system-ui;margin:0;background:#f4f1e8;color:#202018}}main{{max-width:1100px;margin:auto;padding:20px}}img{{display:block;max-width:100%;max-height:65vh;margin:auto;background:#222}}section{{background:white;padding:18px;margin:14px 0;border-radius:10px}}button{{padding:12px 18px;margin:5px;font-weight:700}}input{{padding:10px;width:min(28rem,90%)}}.include{{background:#b8e6b8}}.exclude{{background:#f0b3ad}}.review{{background:#f4dc8b}}small{{overflow-wrap:anywhere}}</style></head><body><main>
<h1>Human curation — {html.escape(stage)} pass</h1><p>{index + 1}/{total} in this queue · first reviewed {summary['total_reviewed']}/{len(_read_csv(manifest_path))}</p>
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
        **{f"split_{key}": value for key, value in sorted(split_counts.items())},
    }
    return _write_report(config, "annotation_audit", counts, blockers)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "collect",
            "export-review",
            "import-review",
            "curate",
            "curation-status",
            "package",
            "build",
            "audit",
        ),
    )
    parser.add_argument("--config", default="configs/detection_dataset.yaml")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--review-id")
    parser.add_argument("--receipt")
    args = parser.parse_args()
    if args.command == "export-review":
        if not args.review_id:
            parser.error("export-review requires --review-id")
        result = export_offline_review(args.config, args.review_id)
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
