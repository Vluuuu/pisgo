# PisGo AI API

Inference service yang menjadi jembatan antara aplikasi fullstack dan model AI.

## Responsibilities

- Receive image + biological inputs from backend.
- Load exported model.
- Run maturity inference.
- Return a stable JSON response that follows `shared/schemas/prediction.schema.json`.
- Hide model implementation details from the web app.

Recommended stack for MVP: Python + FastAPI.

The web app should integrate against the API contract, so frontend/backend development can continue with mock responses while the model is still being trained.
