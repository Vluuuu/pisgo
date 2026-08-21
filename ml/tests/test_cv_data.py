from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
from PIL import Image

from pisgo_ml.cv_data import (
    assert_no_group_leakage,
    assign_grouped_splits,
    build_manifest,
    parse_image_member,
)


LABEL_COLORS = {
    "Unripe": (40, 130, 45),
    "Half_Ripe": (145, 160, 45),
    "Ripe": (225, 190, 35),
    "Overripe": (125, 90, 35),
}


def make_tiny_cv_zip(path: Path) -> Path:
    temporary = path.parent / "images"
    temporary.mkdir()
    with zipfile.ZipFile(path, "w") as archive:
        for label, color in LABEL_COLORS.items():
            for specimen in range(1, 5):
                for view in ("Top", "Bottom"):
                    name = f"Cavendish_{label}_{view}_{specimen:04d}.jpg"
                    image_path = temporary / name
                    Image.new("RGB", (48, 32), color).save(image_path)
                    archive.write(image_path, f"Dataset/Cavendish/{name}")
                    augmented = name.replace(".jpg", "_Aug_1.jpg")
                    augmented_path = temporary / augmented
                    Image.new(
                        "RGB", (48, 32), tuple(min(255, value + 5) for value in color)
                    ).save(augmented_path)
                    archive.write(augmented_path, f"Dataset/Cavendish/{augmented}")
    return path


def test_parse_image_member_extracts_augmentation_family():
    record = parse_image_member(
        "Dataset/Cavendish/Cavendish_Half_Ripe_Bottom_0005_Aug_99.jpg"
    )
    assert record["maturity_class"] == "half_ripe"
    assert record["view"] == "bottom"
    assert record["specimen_id"] == "0005"
    assert record["is_augmented"] is True
    assert record["group_id"] == "cavendish::half_ripe::0005"


def test_manifest_split_has_no_leakage_and_clean_evaluation(tmp_path):
    archive = make_tiny_cv_zip(tmp_path / "tiny.zip")
    manifest = build_manifest(archive, "Cavendish", [label.lower() for label in LABEL_COLORS])
    split = assign_grouped_splits(manifest, 0.5, 0.25, 0.25, 11)

    assert len(split) == 64
    assert_no_group_leakage(split)
    included_eval = split[split["included"] & split["split"].isin(["validation", "test"])]
    assert not included_eval["is_augmented"].any()
    assert split.groupby("group_id")["split"].nunique().max() == 1
    assert set(split["split"]) == {"train", "validation", "test"}
