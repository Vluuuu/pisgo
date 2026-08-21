"""Dataset schema shared by training, evaluation, and inference."""

from __future__ import annotations

ID_COLUMNS = ["record_id", "image_id", "plant_id", "bunch_id"]

REQUIRED_INPUT_COLUMNS = [
    "plant_id",
    "bunch_id",
    "planting_date",
    "flowering_date",
    "photo_date",
]

DATE_COLUMNS = [
    "planting_date",
    "flowering_date",
    "photo_date",
    "harvest_date",
    "shipping_date",
    "arrival_date",
]

TARGET_COLUMNS = ["harvest_date", "arrival_date", "readiness_status"]

RAW_NUMERIC_COLUMNS = [
    "maturity_score",
    "temperature_c",
    "humidity_pct",
    "rainfall_mm_7d",
    "soil_moisture_pct",
    "elevation_m",
    "latitude",
    "longitude",
    "bunch_weight_kg",
    "distance_km",
    "travel_duration_hours",
    "storage_temperature_c",
]

RAW_CATEGORICAL_COLUMNS = [
    "maturity_stage",
    "farm_location",
    "soil_type",
    "irrigation_type",
    "weather_condition",
    "transport_mode",
    "storage_condition",
]

ENGINEERED_NUMERIC_COLUMNS = [
    "plant_age_days",
    "fruit_age_days",
    "planting_to_flowering_days",
    "photo_month_sin",
    "photo_month_cos",
    "travel_duration_days",
    "estimated_speed_kmh",
    "temperature_humidity_index",
]

MODEL_NUMERIC_COLUMNS = RAW_NUMERIC_COLUMNS + ENGINEERED_NUMERIC_COLUMNS
MODEL_CATEGORICAL_COLUMNS = RAW_CATEGORICAL_COLUMNS
MODEL_INPUT_COLUMNS = REQUIRED_INPUT_COLUMNS + RAW_NUMERIC_COLUMNS + RAW_CATEGORICAL_COLUMNS

HARVEST_TARGET = "harvest_days_from_photo"
ARRIVAL_TARGET = "arrival_days_from_photo"
READINESS_TARGET = "readiness_status"

READINESS_CLASSES = ["not_ready", "approaching", "ready", "overdue"]
