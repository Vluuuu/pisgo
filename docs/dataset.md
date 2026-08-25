# Dataset Guidelines

> **Note**: This document outlines the recommended longitudinal agronomic dataset specification for future on-field calibration, not the current YOLO presence gate dataset (which is documented in `ml/datasets/README.md`).

## Scope

Initial MVP focuses on **Cavendish banana** only.

## Preferred collection design

Longitudinal data is preferred over unrelated images from different bananas.

Example:

```text
Bunch A
Flowering → DAF 50 photo → DAF 60 photo → DAF 70 photo → Harvest → Postharvest ripening
```

## Minimum metadata

```text
image_id
plant_id
bunch_id
flowering_date
photo_date
days_after_flowering
maturity_stage
maturity_score
```

Recommended additional metadata:

```text
harvest_date
ripening_date
temperature
humidity
storage_condition
source
camera_device
```

## Splitting rule

Avoid leakage by splitting related images from the same plant/bunch consistently. Images from one longitudinal sequence should not be scattered across train and test in a way that makes evaluation artificially easy.

## Repository storage

Raw images and generated training artifacts are ignored from Git. Store large data externally and document the dataset version/location in `ml/datasets/README.md`.
