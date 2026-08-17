# AI API Contract

This document defines the boundary between PisGo fullstack and the AI/ML service.

## Prediction request

Recommended endpoint:

```text
POST /v1/predict
```

Inputs:

- banana image
- flowering date
- photo date (optional; server can use current date)
- target maturity (optional for current-maturity-only prediction)

Logical request shape:

```json
{
  "flowering_date": "2026-06-01",
  "photo_date": "2026-08-20",
  "target_maturity": 3.0
}
```

The image can be sent using `multipart/form-data` alongside these fields.

## Prediction response

```json
{
  "banana_detected": true,
  "cultivar": "cavendish",
  "days_after_flowering": 80,
  "current_maturity": 2.7,
  "confidence": 0.91,
  "days_to_target": 3.4,
  "model_version": "mock-v1"
}
```

## Rules

- `current_maturity` should use one agreed scale across dataset, ML, backend, and UI.
- `confidence` is normalized from `0` to `1`.
- `days_to_target` can be `null` when no target was requested or prediction is unavailable.
- Breaking response changes require a versioned API contract.

## Web development before model completion

Until the trained model is ready, backend/web can return a mock response using the same schema. This prevents the fullstack and ML workstreams from blocking each other.
