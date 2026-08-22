"""Cavendish image manifest creation and leakage-safe grouped splitting."""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

import numpy as np
import pandas as pd


class CVDatasetError(ValueError):
    """Raised when the image archive does not satisfy the CV data contract."""


_FILENAME_PATTERN = re.compile(
    r"^(?P<variety>.+?)_"
    r"(?P<maturity>Unripe|Half_Ripe|Ripe|Overripe)_"
    r"(?P<view>Top|Bottom|Left|Right)_"
    r"(?P<specimen_id>\d+)"
    r"(?:_Aug_(?P<augmentation_id>\d+))?\.jpg$",
    re.IGNORECASE,
)


def parse_image_member(member: str) -> dict[str, Any]:
    """Parse dataset metadata encoded in one archive member name."""
    name = PurePosixPath(member).name
    match = _FILENAME_PATTERN.fullmatch(name)
    if match is None:
        raise CVDatasetError(f"Unsupported image filename: {member}")

    values = match.groupdict()
    variety = values["variety"].title()
    maturity = values["maturity"].lower()
    specimen_id = values["specimen_id"]
    augmentation_id = values["augmentation_id"]
    return {
        "archive_member": member,
        "filename": name,
        "variety": variety,
        "maturity_class": maturity,
        "view": values["view"].lower(),
        "specimen_id": specimen_id,
        "augmentation_id": augmentation_id,
        "is_augmented": augmentation_id is not None,
        "group_id": f"{variety.lower()}::{maturity}::{specimen_id}",
    }


def build_manifest(
    archive_path: str | Path,
    variety: str = "Cavendish",
    labels: list[str] | None = None,
) -> pd.DataFrame:
    """Read image metadata directly from ZIP without extracting images."""
    source = Path(archive_path)
    if not source.is_file():
        raise FileNotFoundError(f"Image dataset archive not found: {source}")

    normalized_labels = [label.lower() for label in labels] if labels else None
    records: list[dict[str, Any]] = []
    invalid: list[str] = []
    with zipfile.ZipFile(source) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise CVDatasetError(f"Corrupt ZIP member: {bad_member}")
        for info in archive.infolist():
            if info.is_dir() or PurePosixPath(info.filename).suffix.lower() != ".jpg":
                continue
            try:
                record = parse_image_member(info.filename)
            except CVDatasetError:
                invalid.append(info.filename)
                continue
            if record["variety"].casefold() != variety.casefold():
                continue
            if normalized_labels and record["maturity_class"] not in normalized_labels:
                continue
            record["crc32"] = f"{info.CRC:08x}"
            record["file_size"] = info.file_size
            records.append(record)

    if invalid:
        examples = ", ".join(invalid[:3])
        raise CVDatasetError(
            f"Found {len(invalid)} image filename(s) that do not match the dataset schema: {examples}"
        )
    if not records:
        raise CVDatasetError(f"No {variety} images found in {source}")

    manifest = pd.DataFrame.from_records(records).sort_values("archive_member").reset_index(drop=True)
    if normalized_labels:
        missing = sorted(set(normalized_labels) - set(manifest["maturity_class"]))
        if missing:
            raise CVDatasetError(f"Missing maturity classes in archive: {', '.join(missing)}")
    return manifest


def assign_grouped_splits(
    manifest: pd.DataFrame,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    random_state: int,
    train_with_augmented: bool = True,
) -> pd.DataFrame:
    """Stratify specimen groups and keep related views/augmentations together."""
    ratios = np.asarray([train_ratio, validation_ratio, test_ratio], dtype=float)
    if np.any(ratios <= 0) or not np.isclose(ratios.sum(), 1.0):
        raise CVDatasetError("Train, validation, and test ratios must be positive and sum to 1")

    required = {"maturity_class", "group_id", "is_augmented"}
    missing = sorted(required - set(manifest.columns))
    if missing:
        raise CVDatasetError(f"Manifest is missing columns: {', '.join(missing)}")

    rng = np.random.default_rng(random_state)
    group_to_split: dict[str, str] = {}
    for label, class_rows in manifest.groupby("maturity_class", sort=True):
        groups = sorted(class_rows["group_id"].unique())
        if len(groups) < 3:
            raise CVDatasetError(
                f"Class '{label}' needs at least three specimen groups for train/validation/test"
            )
        shuffled = np.asarray(groups, dtype=object)
        rng.shuffle(shuffled)

        raw_counts = ratios * len(shuffled)
        counts = np.floor(raw_counts).astype(int)
        counts[counts == 0] = 1
        while counts.sum() > len(shuffled):
            index = int(np.argmax(counts))
            if counts[index] > 1:
                counts[index] -= 1
        while counts.sum() < len(shuffled):
            remainder = raw_counts - counts
            counts[int(np.argmax(remainder))] += 1

        train_end = counts[0]
        validation_end = train_end + counts[1]
        for group in shuffled[:train_end]:
            group_to_split[str(group)] = "train"
        for group in shuffled[train_end:validation_end]:
            group_to_split[str(group)] = "validation"
        for group in shuffled[validation_end:]:
            group_to_split[str(group)] = "test"

    result = manifest.copy()
    result["split"] = result["group_id"].map(group_to_split)
    result["included"] = True
    if not train_with_augmented:
        result.loc[result["is_augmented"], "included"] = False
    result.loc[
        result["split"].isin(["validation", "test"]) & result["is_augmented"],
        "included",
    ] = False

    included = result[result["included"]]
    if included.empty or included.groupby("split")["maturity_class"].nunique().min() < 1:
        raise CVDatasetError("Split assignment produced an empty split")
    assert_no_group_leakage(result)
    return result


def assert_no_group_leakage(manifest: pd.DataFrame) -> None:
    split_counts = manifest.groupby("group_id")["split"].nunique()
    leaking = split_counts[split_counts > 1]
    if not leaking.empty:
        raise CVDatasetError(f"Specimen groups occur in multiple splits: {leaking.index[:3].tolist()}")
    evaluation_augmented = manifest[
        manifest["included"]
        & manifest["split"].isin(["validation", "test"])
        & manifest["is_augmented"]
    ]
    if not evaluation_augmented.empty:
        raise CVDatasetError("Validation/test splits must not include augmented images")


def archive_fingerprint(archive_path: str | Path, manifest: pd.DataFrame) -> str:
    """Fingerprint archive identity from member metadata without hashing 379 MB of pixels."""
    source = Path(archive_path)
    digest = hashlib.sha256()
    digest.update(str(source.resolve()).encode("utf-8"))
    digest.update(str(source.stat().st_size).encode("ascii"))
    for row in manifest.sort_values("archive_member").itertuples():
        digest.update(f"{row.archive_member}|{row.crc32}|{row.file_size}\n".encode("utf-8"))
    return digest.hexdigest()


def open_archive_member(archive: zipfile.ZipFile, member: str) -> BinaryIO:
    """Open one validated member from an already-open archive."""
    try:
        return archive.open(member, "r")
    except KeyError as error:
        raise CVDatasetError(f"Image member not found in archive: {member}") from error
