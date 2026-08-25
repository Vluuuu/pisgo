# PisGo AI API

FastAPI adapter service between PisGo and machine learning model artifacts.

## Scope & Interpretation

The service accepts a banana photo plus biological dates, enforces a YOLO presence gate, runs the 4-class Cavendish visual maturity classifier, and adapts its output to the PisGo response contract.

Key architectural boundaries:
- **YOLO Presence Gate**: Object detector fine-tuned for `banana_bunch` presence detection. It gates downstream classification to prevent computing maturity on non-banana images.
- **Visual Maturity Classifier**: 4-class image-level classifier (`unripe`, `half_ripe`, `ripe`, `overripe`).
- **Uncalibrated Confidence**: `confidence` is the classifier's maximum softmax score, not a calibrated real-world probability.
- **DAF Biological Age**: Computed deterministically from `photo_date` and `flowering_date`.

## Four Classes to UI Scale (1–7)

The classifier's raw classes are mapped to PisGo's 1–7 UI scale using configurable anchors:

| Visual Class | PisGo UI Anchor |
|---|---:|
| `unripe` | 2.0 |
| `half_ripe` | 3.5 |
| `ripe` | 5.5 |
| `overripe` | 6.5 |

This is a **PisGo design mapping**, not an agronomic calibration. `current_maturity` is calculated as the probability-weighted blend:

$$\text{current\_maturity} = \sum_{c \in \text{classes}} P(c) \times \text{anchor}(c)$$

The response preserves `debug.predicted_class`, `debug.class_probabilities`, and `debug.maturity_class_scale` for full traceability.

## Presence Gate & Fail-Closed Behavior

When `banana_detected = false`:
- `current_maturity` is `null`;
- `confidence` is `null`;
- `days_to_target` is `null`;
- Classifier outputs in `debug` (`predicted_class`, `class_probabilities`, etc.) are `null`;
- `days_after_flowering` is computed honestly from the supplied dates;
- Detector debug metadata (`detector_model_version`, `detection_count: 0`, `detector_inference_milliseconds`) is preserved.

The service never fabricates a maturity rating for an image without a detected banana bunch.

## Required Local Artifacts

The binary model artifacts are excluded from Git:
1. `ml/models/banana_bunch_yolo11n_emergency_v1.pt` (YOLO presence gate)
2. `ml/models/cavendish_maturity_classifier.joblib` (4-class visual classifier)

Download artifacts from GitHub Release `aic-preliminary-models-v1`:
```bash
gh release download aic-preliminary-models-v1 --dir ml/models
```

## Running the Service

```bash
# From repository root
pip install -e ./ml
pip install -r ./services/ai-api/requirements.txt

uvicorn app.main:app --app-dir ./services/ai-api --host 0.0.0.0 --port 8001
```

Health check endpoint: `GET /health`

## Endpoint Definition

```text
POST /v1/predict
Content-Type: multipart/form-data
```

| Field | Type | Rules |
|---|---|---|
| `flowering_date` | string (`YYYY-MM-DD`) | Required |
| `photo_date` | string (`YYYY-MM-DD`) | Required; $\ge \text{flowering\_date}$ |
| `target_maturity` | float | Required; range `[1.0, 7.0]` |
| `image` | binary image file | Required; max 10 MB |
