"""FastAPI application for the PisGo AI adapter service."""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

from pisgo_ml.cv_features import CVFeatureError
from pisgo_ml.cv_predict import CVArtifactError, load_cv_artifact

from .adapter import BananaPredictor
from .config import load_settings
from .schemas import ErrorResponse, HealthResponse, PredictionResponse

app = FastAPI(
    title="PisGo AI API",
    version="1.0.0",
    description=(
        "Adapter service between the PisGo web app and the Cavendish maturity "
        "classifier. Banana detection is a heuristic proxy; confidence is an "
        "uncalibrated score; the class->1-7 maturity mapping is a PisGo design "
        "decision, not an agronomic calibration."
    ),
)

_settings = load_settings()
_predictor: BananaPredictor | None = None
_load_error: str | None = None

try:
    _predictor = BananaPredictor(load_cv_artifact(_settings.model_path), _settings)
except (FileNotFoundError, CVArtifactError) as exc:  # pragma: no cover
    _load_error = str(exc)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok" if _predictor is not None else "model_not_loaded",
        model_version=_predictor.model_version if _predictor else "unavailable",
        adapter_version=_settings.adapter_version,
        model_loaded=_predictor is not None,
    )


@app.post(
    "/v1/predict",
    response_model=PredictionResponse,
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def predict(
    flowering_date: date = Form(...),
    photo_date: date = Form(...),
    target_maturity: float = Form(...),
    image: UploadFile = File(...),
) -> PredictionResponse | JSONResponse:
    if _predictor is None:
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                error=f"Model artifact not loaded: {_load_error}"
            ).model_dump(),
        )

    if not (1.0 <= target_maturity <= 7.0):
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error="target_maturity must be between 1 and 7."
            ).model_dump(),
        )

    if photo_date < flowering_date:
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error="photo_date must not be earlier than flowering_date."
            ).model_dump(),
        )

    if image.content_type and not image.content_type.startswith("image/"):
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(error="image must be an image file.").model_dump(),
        )

    image_bytes = await image.read()
    if not image_bytes:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(error="image file is empty.").model_dump(),
        )
    if len(image_bytes) > _settings.max_image_bytes:
        return JSONResponse(
            status_code=413,
            content=ErrorResponse(
                error="image must be 10 MB or smaller."
            ).model_dump(),
        )

    try:
        return _predictor.predict(
            image_bytes=image_bytes,
            flowering_date=flowering_date,
            photo_date=photo_date,
            target_maturity=target_maturity,
        )
    except CVFeatureError as exc:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(error=f"Unreadable image: {exc}").model_dump(),
        )


def main() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=False)


if __name__ == "__main__":  # pragma: no cover
    main()
