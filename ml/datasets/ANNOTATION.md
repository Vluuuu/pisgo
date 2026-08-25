# YOLO Annotation Contract

> **Historical Note**: This document records the original annotation-gate contract and data quality specification. The `YOLO_DATASET_BLOCKED` status below describes the original standard dataset workflow before the competition emergency baseline was finalized. The currently deployed detector and its evaluated dataset are documented in `ml/README.md` and `ml/datasets/README.md`.

## Status

`YOLO_DATASET_BLOCKED`: training is prohibited until a verified bounding-box export satisfies this contract. The current Augmented Banana Variety Dataset contains image-level maturity labels only; it has no verified object annotations.

## Class

```text
0 banana_bunch
```

Annotate every visible whole banana bunch with one axis-aligned box. The class represents a bunch, not an individual fruit or banana hand.

## Box rules

- Draw the tightest practical rectangle around visible bunch pixels, including visible fruit and the bunch stalk when it is clearly attached.
- Annotate each distinct bunch once when multiple bunches are visible.
- Annotate partially visible or occluded bunches when their visible pixels are unambiguously a banana bunch; box only the visible extent and never infer hidden pixels.
- Annotate a bunch touching an image edge using only its visible extent.
- Skip objects that are too small or blurred to identify confidently as a banana bunch.
- Do not box individual fruits, hands, leaves, trunks, people, labels, or background objects.
- Images reviewed as containing no identifiable banana bunch are negative examples and receive an empty label file.

## Accepted export

Use matching relative paths and filename stems:

```text
images/train/example.jpg
labels/train/example.txt
images/val/example.jpg
labels/val/example.txt
images/test/example.jpg
labels/test/example.txt
```

Each UTF-8 label row uses native YOLO normalized coordinates:

```text
class_id x_center y_center width height
```

All four coordinates are relative to image width or height and must be finite values in `[0, 1]`. Width and height must be greater than zero, and the resulting box must remain within the image. Only class ID `0` is valid. One object occupies one line; an empty file denotes a verified negative image.

## Source and split policy

- Label original images only. Do not independently label the existing `_Aug_*` descendants.
- Any future augmentation must transform pixels and bounding boxes together after the split is assigned.
- Assign every source image an explicit `specimen_id` and `group_id`; keep every view, exact duplicate, and descendant of one specimen in one partition.
- For the existing archive, the group key remains `variety + maturity_class + specimen_id`. For multi-source field photos, use a conservative source/specimen group and regroup related views before building the dataset.
- Do not derive train, validation, and test membership independently per image.
- Keep external field photos outside supervised scoring until their provenance is recorded and a human reviews and labels them under this contract.

## Human curation gate

Before packaging, every candidate receives an explicit first-pass `include`, `exclude`, or `needs_review` decision. A remote Reviewer 1 may use the generated portable offline bundle: extract its ZIP, open `index.html`, enter reviewer identity, inspect each image, download the JSON receipt, and return that receipt for validated import. Unreviewed candidates are omitted from the receipt and remain unresolved. The bundle and receipt are local generated data and must not be committed. The UI is only a human review aid: it does not classify images or generate boxes. After first pass, every `needs_review` row and a deterministic sample of at least 10% of include decisions per candidate role require a second human whose identity differs from the first reviewer. Spot-check disagreement and unresolved uncertainty remain `needs_review`; they are never silently resolved. Packaging stays blocked until all required reviews are complete, unresolved count is zero, and a human creates the hash-bound final approval.

## Human review receipts

A tool export is not proof that an empty or missing label is a negative. Return these files with the YOLO labels:

- `review.csv`: one row per candidate with `image_id`, `final_status` (`positive`, `negative`, or `exclude`), `task_id`, `reviewer`, and `reviewed_at`.
- `human_qa.csv`: reviewed examples covering `positive`, `negative`, `partial`, `occluded`, `edge_touching`, and `multi_bunch`.

Every included positive must have at least one box. Every included negative must have an explicit `negative` receipt and an empty UTF-8 label file. Pending, missing, or mismatched records remain blocked.

## Training acceptance checklist

Training may start only after all items pass:

- [ ] Dataset source, version, license, and permission to use are recorded.
- [ ] Every image has one matching label file, including reviewed negatives.
- [ ] Every non-empty row has exactly five fields and class ID `0`.
- [ ] Coordinates are finite and normalized; boxes are non-degenerate and in bounds.
- [ ] Duplicate boxes and unintended overlapping duplicates are removed.
- [ ] Negative images were explicitly reviewed rather than inferred from missing files.
- [ ] Original/augmented relationships and specimen groups do not cross splits.
- [ ] A human spot-check covers positive, negative, partial, occluded, edge-touching, and multi-bunch examples.
- [ ] The export contains at least one valid positive box in each intended split.

Missing or invalid annotations keep the task in `YOLO_DATASET_BLOCKED`; they must never be replaced with filename-derived, full-image, heuristic, or synthetic boxes.
