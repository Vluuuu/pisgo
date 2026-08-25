# AI API Contract

This document defines the interface between the PisGo web application and the FastAPI AI inference service.

## Prediction Endpoint

```text
POST /v1/predict
Content-Type: multipart/form-data
```

### Required Fields

| Field | Type | Description | Rules |
|---|---|---|---|
| `flowering_date` | Form string | Date of flowering (`YYYY-MM-DD`) | Required; $\le \text{photo\_date}$ |
| `photo_date` | Form string | Date when specimen photo was taken (`YYYY-MM-DD`) | Required |
| `target_maturity` | Form number | Target maturity at destination | Required; float in range `[1.0, 7.0]` |
| `image` | File | Cavendish banana bunch photo | Required; valid image (JPG, PNG, WebP) $\le 10\text{ MB}$ |

## Prediction Pipeline & Response

1. **Banana Bunch Presence Gate (YOLOv11n)**: The uploaded image is first checked for class-0 (`banana_bunch`) detection at confidence threshold $\ge 0.25$.
2. **Visual Maturity Inference (Cavendish 4-Class)**: If a banana bunch is detected, original image bytes are passed to the 4-class visual classifier. If no banana bunch is detected, maturity classification is bypassed.

### Response on Banana Detected (`banana_detected: true`)

```json
{
  "banana_detected": true,
  "cultivar": "cavendish",
  "days_after_flowering": 80,
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
    "detector_model_version": "banana-bunch-yolo11n-emergency-v1",
    "detection_score": 0.92,
    "detection_count": 1,
    "detection_threshold": 0.25,
    "detection_method": "yolo11n-class-0",
    "detector_inference_milliseconds": 14.2,
    "inference_milliseconds": 11.7
  }
}
```

### Response on No Banana Detected (`banana_detected: false`)

```json
{
  "banana_detected": false,
  "cultivar": "cavendish",
  "days_after_flowering": 80,
  "current_maturity": null,
  "confidence": null,
  "days_to_target": null,
  "model_version": "cavendish-color-texture-v1",
  "adapter_version": "pisgo-ai-api-v1",
  "debug": {
    "predicted_class": null,
    "class_probabilities": null,
    "maturity_class_scale": null,
    "detector_model_version": "banana-bunch-yolo11n-emergency-v1",
    "detection_score": null,
    "detection_count": 0,
    "detection_threshold": 0.25,
    "detection_method": "yolo11n-class-0",
    "detector_inference_milliseconds": 10.0,
    "inference_milliseconds": null
  }
}
```

The canonical JSON Schema contract is maintained at `shared/schemas/prediction.schema.json`.
