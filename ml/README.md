# PisGo ML — Cavendish Harvest & Arrival Predictor

Pipeline machine learning tabular untuk memperkirakan tanggal panen, tanggal kedatangan, dan status kesiapan panen pisang Cavendish. Implementasi ini adalah baseline operasional untuk data agronomi, usia tanaman/buah, cuaca, lokasi, dan logistik. Pipeline computer vision/foto belum termasuk dalam versi ini.

## Output model

Training menghasilkan satu artifact persisten:

```text
models/cavendish_predictor.joblib
```

Artifact Joblib memuat feature engineering, imputasi missing value, one-hot encoder, dua Random Forest regressor, readiness classifier, metadata fitur, versi runtime, dan metrik. Inference hanya memuat artifact tersebut; inference tidak melakukan training atau preprocessing fit ulang.

## Instalasi

Jalankan dari folder `ml`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Alternatif tanpa editable install:

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
```

Linux/macOS menggunakan `export PYTHONPATH=src`.

## Struktur

```text
ml/
├── configs/default.yaml
├── data/sample/cavendish_sample.csv
├── data/sample/cavendish_inference_sample.csv
├── models/
├── reports/
├── src/pisgo_ml/
│   ├── config.py
│   ├── data.py
│   ├── evaluate.py
│   ├── features.py
│   ├── predict.py
│   ├── schema.py
│   ├── synthetic.py
│   ├── train.py
│   └── utils.py
└── tests/
```

## Skema dataset

Kolom input wajib:

| Kolom | Tipe | Keterangan |
|---|---|---|
| `plant_id` | string | ID tanaman |
| `bunch_id` | string | ID tandan; dipakai untuk split tanpa leakage |
| `planting_date` | `YYYY-MM-DD` | tanggal tanam |
| `flowering_date` | `YYYY-MM-DD` | tanggal flowering |
| `photo_date` | `YYYY-MM-DD` | tanggal observasi/referensi prediksi |

Kolom fitur opsional (dibuat missing-safe):

- Visual/observasi: `image_id`, `maturity_stage`, `maturity_score`.
- Cuaca/kebun: `temperature_c`, `humidity_pct`, `rainfall_mm_7d`, `soil_moisture_pct`, `weather_condition`.
- Lokasi/agronomi: `farm_location`, `elevation_m`, `latitude`, `longitude`, `soil_type`, `irrigation_type`, `bunch_weight_kg`.
- Logistik: `distance_km`, `travel_duration_hours`, `transport_mode`, `storage_condition`, `storage_temperature_c`.

Kolom target wajib untuk training/evaluasi:

| Kolom | Keterangan |
|---|---|
| `harvest_date` | tanggal panen aktual |
| `arrival_date` | tanggal tiba aktual |
| `readiness_status` | opsional: `not_ready`, `approaching`, `ready`, atau `overdue` |

`shipping_date` boleh disimpan sebagai metadata, tetapi bukan target model saat ini. Dataset harus memenuhi `planting_date <= flowering_date <= photo_date <= harvest_date <= arrival_date`.

## Feature engineering dan preprocessing

1. Parsing dan validasi tanggal.
2. `plant_age_days`, `fruit_age_days`, dan `planting_to_flowering_days`.
3. Encoding siklus bulan (`sin`/`cos`).
4. Durasi perjalanan dalam hari dan estimasi kecepatan.
5. Interaksi suhu-kelembapan sederhana.
6. Imputasi median untuk numerik.
7. Imputasi modus dan `OneHotEncoder(handle_unknown="ignore")` untuk kategorikal.
8. Group split berdasarkan `bunch_id`, sehingga observasi satu tandan tidak tersebar ke train dan test.

Target regresi adalah jumlah hari kalender dari `photo_date` ke panen dan kedatangan. Inference mengonversinya kembali menjadi tanggal.

## Data sintetis

File `data/sample/cavendish_sample.csv` hanya untuk smoke test, bukan bukti performa agronomi nyata. Buat ulang dengan:

```powershell
python -m pisgo_ml.synthetic --output data/sample/cavendish_sample.csv --rows 80
```

## Training

```powershell
python -m pisgo_ml.train --config configs/default.yaml
```

Output:

- `models/cavendish_predictor.joblib`
- `reports/training_metrics.json`

Baseline menggunakan `DummyRegressor(strategy="median")`; model utama menggunakan Random Forest. Parameter dan seluruh path dapat diubah di `configs/default.yaml`.

## Evaluasi

```powershell
python -m pisgo_ml.evaluate --config configs/default.yaml
```

Output `reports/evaluation_metrics.json`. Perintah ini tidak melakukan training ulang. Gunakan CSV held-out yang benar-benar terpisah untuk evaluasi final:

```powershell
python -m pisgo_ml.evaluate --config configs/default.yaml --data data/held_out.csv
```

Metrik regresi: MAE, RMSE, R². Metrik klasifikasi: accuracy, precision, recall, dan F1 weighted.

## Prediksi tanpa training ulang

```powershell
python -m pisgo_ml.predict --config configs/default.yaml --input data/sample/cavendish_inference_sample.csv --output reports/predictions.csv
```

Model dan preprocessing terlatih langsung dimuat dari Joblib. Input inference tidak perlu memiliki kolom target. Raw output tidak mengikuti schema frontend; adapter aplikasi dapat dibuat terpisah.

Kolom output:

```text
record_id,image_id,plant_id,bunch_id,prediction_reference_date,
predicted_harvest_days_from_photo,predicted_harvest_date,
predicted_arrival_days_from_photo,predicted_arrival_date,
predicted_readiness_status,readiness_confidence,model_version
```

## Test

```powershell
python -m pytest -q
```

Test mencakup loading/validasi, group split, feature engineering, missing-value preprocessing, training kecil, penyimpanan/pemuatan artifact, dan output prediksi CSV.

## Batasan

- Performa sample berasal dari data sintetis dan tidak boleh digunakan sebagai klaim performa produksi.
- Dataset asli longitudinal per tanaman/tandan wajib disiapkan untuk training yang valid.
- Foto saat ini hanya dapat direferensikan melalui `image_id`; piksel foto belum diproses. Integrasi computer vision membutuhkan model dan pipeline terpisah.
- Artifact Joblib sebaiknya hanya dimuat dari sumber tepercaya karena format pickle dapat mengeksekusi kode saat deserialisasi.
