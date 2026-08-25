# Dataset Registry

Large dataset binaries and raw rasters are intentionally excluded from Git.

## 1. Banana Bunch Detection Dataset (YOLOv11n)

Used for training and evaluating the frozen `banana-bunch-yolo11n-emergency-v1` presence gate.

- **Curated Dataset Total**: 322 verified images
  - **Valid Positive (`banana_bunch`)**: 241 images
  - **Verified Hard-Negative (Background/Non-Banana)**: 81 images
- **Dataset Partitions**: Grouped split (~70% train, ~15% validation, ~15% held-out test)
- **Dedicated Held-Out Test Set**: 48 images (36 positive, 12 verified hard-negative)
- **Provenance & Licensing**: Sourced from Wikimedia Commons under explicit `CC0`, `CC BY`, and `CC BY-SA` licenses with provenance metadata.
- **Workflow & Evaluation Configuration**: `ml/configs/detection_emergency_baseline.yaml`.

*Note on Historical Context: The standard long-term annotation workflow ([ANNOTATION.md](ANNOTATION.md)) previously used a strict `YOLO_DATASET_BLOCKED` gate until human annotation and double-blind review was completed. The competition emergency baseline finalized this curation workflow for the deployed YOLOv11n model.*

---

## 2. Augmented Banana Variety Dataset (Maturity Classifier)

Used for training the 4-class Cavendish visual maturity classifier.

- **Format**: Image-level classification dataset with 4 maturity classes (`unripe`, `half_ripe`, `ripe`, `overripe`).
- **Cavendish Subset**: 1,750 images across 95 specimen groups (380 original studio captures + 1,370 controlled augmentations).
- **Split Policy**: Grouped by `variety + maturity_class + specimen_id` so that original captures and augmented descendants from the same specimen remain strictly in the same split. Validation and test sets use original images only.

---

## 3. Tabular Dataset Baseline

Sample CSVs under `data/sample/` are synthetic scaffolds used for contract testing. Field agronomic deployment requires longitudinal tracking per plant/bunch.
