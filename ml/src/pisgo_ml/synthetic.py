"""Deterministic synthetic data for smoke tests and examples only."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .schema import READINESS_CLASSES


def _readiness(days_to_harvest: int) -> str:
    if days_to_harvest > 18:
        return READINESS_CLASSES[0]
    if days_to_harvest > 7:
        return READINESS_CLASSES[1]
    if days_to_harvest >= 0:
        return READINESS_CLASSES[2]
    return READINESS_CLASSES[3]


def generate_synthetic_dataset(rows: int = 80, seed: int = 42) -> pd.DataFrame:
    if rows < 12:
        raise ValueError("Synthetic dataset requires at least 12 rows")

    rng = np.random.default_rng(seed)
    records: list[dict[str, object]] = []
    locations = [
        ("Lampung", -5.45, 105.27, 120.0),
        ("Jember", -8.17, 113.70, 90.0),
        ("Banyuwangi", -8.22, 114.37, 70.0),
        ("Sukabumi", -6.92, 106.93, 520.0),
    ]
    soils = ["loam", "clay_loam", "sandy_loam"]
    weather = ["sunny", "cloudy", "rainy"]
    transports = ["truck_ambient", "reefer_truck"]

    for index in range(rows):
        bunch_number = index // 2
        photo_offset = (index % 2) * 8
        farm, latitude, longitude, elevation = locations[bunch_number % len(locations)]
        planting_date = pd.Timestamp("2025-01-05") + pd.Timedelta(days=bunch_number * 3)
        flowering_days = int(rng.integers(205, 245))
        flowering_date = planting_date + pd.Timedelta(days=flowering_days)
        fruit_age = int(rng.integers(54, 94)) + photo_offset
        photo_date = flowering_date + pd.Timedelta(days=fruit_age)

        temperature = float(np.clip(rng.normal(27.2, 2.0), 21, 33))
        humidity = float(np.clip(rng.normal(78, 8), 55, 96))
        rainfall = float(max(0, rng.normal(32, 25)))
        soil_moisture = float(np.clip(rng.normal(62, 10), 30, 90))
        maturity_score = float(
            np.clip(1.0 + (fruit_age - 50) / 12 + (temperature - 27) * 0.08, 1, 7)
        )

        base_harvest_age = 91 + (28 - temperature) * 1.1 + (rainfall - 30) * 0.025
        days_to_harvest = int(round(base_harvest_age - fruit_age + rng.normal(0, 2.0)))
        days_to_harvest = max(-4, days_to_harvest)
        harvest_date = photo_date + pd.Timedelta(days=max(0, days_to_harvest))

        distance = float(rng.integers(80, 900))
        travel_hours = distance / float(rng.uniform(42, 58)) + float(rng.uniform(2, 7))
        shipping_delay = int(rng.integers(0, 2))
        shipping_date = harvest_date + pd.Timedelta(days=shipping_delay)
        transit_days = max(1, int(np.ceil(travel_hours / 24)))
        arrival_date = shipping_date + pd.Timedelta(days=transit_days)
        readiness = _readiness(days_to_harvest)

        if maturity_score < 2.2:
            stage = "immature"
        elif maturity_score < 3.8:
            stage = "developing"
        elif maturity_score < 5.5:
            stage = "mature_green"
        else:
            stage = "ripe"

        records.append(
            {
                "record_id": f"rec_{index + 1:04d}",
                "image_id": f"img_{index + 1:04d}.jpg",
                "plant_id": f"plant_{bunch_number + 1:03d}",
                "bunch_id": f"bunch_{bunch_number + 1:03d}",
                "planting_date": planting_date.date().isoformat(),
                "flowering_date": flowering_date.date().isoformat(),
                "photo_date": photo_date.date().isoformat(),
                "maturity_stage": stage,
                "maturity_score": round(maturity_score, 2),
                "temperature_c": round(temperature, 1),
                "humidity_pct": round(humidity, 1),
                "rainfall_mm_7d": round(rainfall, 1),
                "soil_moisture_pct": round(soil_moisture, 1),
                "farm_location": farm,
                "elevation_m": elevation,
                "latitude": latitude,
                "longitude": longitude,
                "soil_type": soils[bunch_number % len(soils)],
                "irrigation_type": "drip" if bunch_number % 2 == 0 else "rainfed",
                "weather_condition": weather[index % len(weather)],
                "bunch_weight_kg": round(float(rng.normal(27, 4)), 1),
                "distance_km": round(distance, 1),
                "travel_duration_hours": round(travel_hours, 1),
                "transport_mode": transports[index % len(transports)],
                "storage_condition": "cooled" if index % 2 else "ambient",
                "storage_temperature_c": 14.0 if index % 2 else 25.0,
                "harvest_date": harvest_date.date().isoformat(),
                "shipping_date": shipping_date.date().isoformat(),
                "arrival_date": arrival_date.date().isoformat(),
                "readiness_status": readiness,
            }
        )

    frame = pd.DataFrame.from_records(records)
    missing_rows = frame.index[::11]
    frame.loc[missing_rows, "rainfall_mm_7d"] = np.nan
    frame.loc[frame.index[::13], "soil_moisture_pct"] = np.nan
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/sample/cavendish_sample.csv")
    parser.add_argument("--rows", type=int, default=80)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    generate_synthetic_dataset(args.rows, args.seed).to_csv(output, index=False)
    print(f"Wrote {args.rows} synthetic rows to {output}")


if __name__ == "__main__":
    main()
