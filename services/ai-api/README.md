# PisGo AI API

FastAPI adapter between PisGo and the persisted Cavendish visual-maturity classifier.

## Scope and interpretation

The service accepts a photo plus biological dates, runs the persisted four-class classifier, and adapts its result to the PisGo response contract.

Important limitations:

- Banana presence is a **heuristic/proxy**, derived from the classifier feature `foreground_proxy_ratio`. It is not a separately trained or field-validated object detector.
- `confidence` is an **uncalibrated score**: the maximum probability emitted by the classifier. It must not be interpreted as calibrated real-world certainty.
- The source training data is controlled and limited. Its evaluation result is not a claim of field or agronomic accuracy.
- The synthetic tabular baseline is not used by this endpoint and is not evidence of agronomic accuracy.
- The PisGo optimizer is not used or modified by this service.

## Four classes to UI scale 1-7

The classifier's raw classes are mapped to PisGo's UI scale using these configurable anchors:

| Visual class | PisGo UI anchor |
| --- | ---: |
| `unripe` | 2.0 |
| `half_ripe` | 3.5 |
| `ripe` | 5.5 |
| `overripe` | 6.5 |

This is a **PisGo design mapping**, not an agronomic calibration. `current_maturity` is the probability-weighted blend:

```text
sum(class_probability[class] * ui_anchor[class])
```

The response always retains `debug.predicted_class`, `debug.class_probabilities`, and `debug.maturity_class_scale`. For example, a displayed value such as 5.2 is therefore traceable to the raw four-class probabilities rather than being an unexplained direct model output.

Override the anchors without changing code:

```powershell
$env:MATURITY_CLASS_SCALE_JSON = '{"unripe":2.0,"half_ripe":3.5,"ripe":5.5,"overripe":6.5}'
```

## Explicit no-banana behavior

When the heuristic/proxy reports `banana_detected: false`:

- `current_maturity` is `null`;
- `confidence` is `null`;
- `days_to_target` is `null`;
- raw four-class classifier output remains in `debug` solely for traceability;
- `days_after_flowering` is still computed from the supplied dates.

The service never fabricates a maturity value for an input that fails the banana-presence heuristic.

## Required local artifact

The binary model is intentionally excluded from Git:

```text
ml/models/cavendish_maturity_classifier.joblib
```

Expected artifact metadata:

```text
artifact_format: pisgo_ml.cv.joblib
artifact_version: 1
model_version: cavendish-color-texture-v1
```

Create it using the ML handoff instructions in `ml/HANDOFF.md`, or place a trusted copy at the path above. An alternative path may be set with `CV_MODEL_PATH`.

Never load an untrusted `.joblib` file: Joblib/Pickle deserialization can execute code.

## Install

From the repository root:

```powershell
python -m pip install -e .\ml
python -m pip install -r .\services\ai-api\requirements.txt
```

For tests:

```powershell
python -m pip install pytest httpx jsonschema
```

## Run FastAPI

From the repository root:

```powershell
python -m uvicorn app.main:app --app-dir .\services\ai-api --host 0.0.0.0 --port 8001
```

Health check:

```powershell
curl.exe http://localhost:8001/health
```

Interactive OpenAPI documentation is available at `http://localhost:8001/docs`.

## Endpoint

```text
POST /v1/predict
Content-Type: multipart/form-data
```

### Exact request fields

| Field | Multipart type | Rules |
| --- | --- | --- |
| `flowering_date` | string (`YYYY-MM-DD`) | required |
| `photo_date` | string (`YYYY-MM-DD`) | required; not before flowering date |
| `target_maturity` | number | required; 1-7 |
| `image` | image file | required; non-empty; maximum 10 MiB |

Multipart requests do not have a single JSON request body. The exact equivalent field object is:

```json
{
  "flowering_date": "2026-08-01",
  "photo_date": "2026-08-22",
  "target_maturity": 6.5,
  "image": "<binary image file>"
}
```

### Example curl

```powershell
curl.exe -X POST "http://localhost:8001/v1/predict" `
  -F "flowering_date=2026-08-01" `
  -F "photo_date=2026-08-22" `
  -F "target_maturity=6.5" `
  -F "image=@D:\photos\cavendish.jpg;type=image/jpeg"
```

### Exact successful response shape

Numeric values below are an example; actual probabilities and inference time depend on the image and runtime.

```json
{
  "banana_detected": true,
  "cultivar": "cavendish",
  "days_after_flowering": 21,
  "current_maturity": 3.501,
  "confidence": 0.9997,
  "days_to_target": 19.99,
  "model_version": "cavendish-color-texture-v1",
  "adapter_version": "pisgo-ai-api-v1",
  "debug": {
    "predicted_class": "half_ripe",
    "class_probabilities": {
      "unripe": 0.00000005,
      "half_ripe": 0.99973179,
      "ripe": 0.00000207,
      "overripe": 0.00026609
    },
    "maturity_class_scale": {
      "unripe": 2.0,
      "half_ripe": 3.5,
      "ripe": 5.5,
      "overripe": 6.5
    },
    "foreground_proxy_ratio": 0.080933,
    "banana_detection_threshold": 0.02,
    "detection_method": "foreground-color-heuristic-proxy",
    "inference_milliseconds": 11.701
  }
}
```

### Exact no-banana response shape

```json
{
  "banana_detected": false,
  "cultivar": "cavendish",
  "days_after_flowering": 21,
  "current_maturity": null,
  "confidence": null,
  "days_to_target": null,
  "model_version": "cavendish-color-texture-v1",
  "adapter_version": "pisgo-ai-api-v1",
  "debug": {
    "predicted_class": "half_ripe",
    "class_probabilities": {
      "unripe": 0.0,
      "half_ripe": 1.0,
      "ripe": 0.0,
      "overripe": 0.0
    },
    "maturity_class_scale": {
      "unripe": 2.0,
      "half_ripe": 3.5,
      "ripe": 5.5,
      "overripe": 6.5
    },
    "foreground_proxy_ratio": 0.0,
    "banana_detection_threshold": 0.02,
    "detection_method": "foreground-color-heuristic-proxy",
    "inference_milliseconds": 8.973
  }
}
```

The machine-readable response contract is `shared/schemas/prediction.schema.json`.

## `days_to_target`

For detected inputs only, this MVP uses a documented linear adapter heuristic:

```text
(target_maturity - current_maturity) / 0.15
```

It returns `null` when the target is already reached/passed or no banana is detected. The rate is configurable through `MATURITY_RATE_PER_DAY`; it is a temporary product heuristic and not an agronomic model.

## Configuration

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `CV_MODEL_PATH` | `ml/models/cavendish_maturity_classifier.joblib` | trusted CV artifact path |
| `MATURITY_CLASS_SCALE_JSON` | mapping table above | four-class to UI-scale design anchors |
| `MATURITY_RATE_PER_DAY` | `0.15` | temporary linear `days_to_target` rate |
| `BANANA_FOREGROUND_MIN_RATIO` | `0.02` | banana-presence heuristic threshold |

## Test

From the repository root:

```powershell
python -m pytest .\services\ai-api\tests -v
```

The API tests use generated in-memory images, so the dataset ZIP is not required. The ignored model artifact is required; artifact-free environments still run the pure adapter tests, while artifact-dependent endpoint tests are skipped.
