# PisGo ML — Cavendish Harvest & Arrival Predictor

Proyek machine learning untuk pisang Cavendish dengan dua pipeline terpisah: model tabular untuk memperkirakan tanggal panen/arrival dan baseline computer vision untuk mengklasifikasikan kematangan foto menjadi `unripe`, `half_ripe`, `ripe`, atau `overripe`. Keduanya menyimpan preprocessing dan model sebagai artifact persisten sehingga inference tidak melakukan training ulang.

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

## Computer vision: klasifikasi kematangan foto

Baseline CV membaca gambar langsung dari ZIP tanpa mengekstrak dataset. Konfigurasi berada di `configs/cv_baseline.yaml`. Dataset yang digunakan memiliki nama file seperti:

```text
Cavendish_Half_Ripe_Bottom_0001_Aug_1141.jpg
```

Metadata filename dipakai untuk membentuk label, view, specimen ID, dan keluarga augmentasi. Split dilakukan berdasarkan `variety + maturity_class + specimen_id`, sehingga semua view dan augmentasi dari spesimen yang sama selalu berada pada partition yang sama. Validation dan test hanya menggunakan gambar original.

Training:

```powershell
python -m pisgo_ml.cv_train --config configs/cv_baseline.yaml
```

Output:

- `models/cavendish_maturity_classifier.joblib`
- `reports/cv_manifest.csv`
- `reports/cv_metrics.json`

Model ini menggunakan fitur RGB/HSV, statistik warna spasial, edge, dan tekstur ringan, lalu `StandardScaler` + multinomial logistic regression. Ini adalah classifier tingkat gambar, bukan object detector; YOLO belum digunakan karena dataset tidak memiliki bounding box.

Inference file foto biasa:

```powershell
python -m pisgo_ml.cv_predict --config configs/cv_baseline.yaml --image path/to/photo.jpg
```

Inference langsung terhadap satu file di dalam ZIP:

```powershell
python -m pisgo_ml.cv_predict --config configs/cv_baseline.yaml `
  --member "Augmented Banana Variety Dataset/Cavendish/Cavendish_Ripe_Top_0002.jpg"
```

Raw JSON mencakup `predicted_class`, `confidence`, probabilitas empat kelas, preprocessing, versi model, dan waktu inference. Script hanya memuat artifact terlatih dan tidak melakukan training ulang.

### Dataset deteksi `banana_bunch`

Dataset object detection adalah workflow terpisah dan tetap berstatus `YOLO_DATASET_BLOCKED` sampai anotasi dan QA manusia lengkap. Konfigurasi provenance-first berada di `configs/detection_dataset.yaml`:

```powershell
python -m pisgo_ml.detection_dataset --config configs/detection_dataset.yaml collect
python -m pisgo_ml.detection_dataset --config configs/detection_dataset.yaml export-review --review-id reviewer-1
python -m pisgo_ml.detection_dataset --config configs/detection_dataset.yaml import-review --receipt path/to/reviewer-1-receipt.json
python -m pisgo_ml.detection_dataset --config configs/detection_dataset.yaml curate
python -m pisgo_ml.detection_dataset --config configs/detection_dataset.yaml curation-status
python -m pisgo_ml.detection_dataset --config configs/detection_dataset.yaml package
python -m pisgo_ml.detection_dataset --config configs/detection_dataset.yaml build
python -m pisgo_ml.detection_dataset --config configs/detection_dataset.yaml audit
```

`collect` hanya menerima raster original Wikimedia Commons berlisensi `CC0`, `CC BY`, atau `CC BY-SA`, mencatat URL/author/license/hash, dan menolak metadata lisensi yang tidak lengkap. Search role hanya membantu kurasi; bukan label. `export-review` membuat ZIP lokal mandiri berisi review copies dan HTML offline; Reviewer 1 mengekstrak ZIP, membuka `index.html`, memasukkan identitas, meninjau gambar, lalu mengirim kembali `reviewer-1-receipt.json`. `import-review` memvalidasi digest kandidat, ID, keputusan, reviewer, timestamp, duplikasi, dan skema receipt sebelum mengubah hanya state kurasi; baris yang tidak direview tetap unresolved. `curate` tetap menjadi UI localhost untuk Reviewer 2. Semua `needs_review` dan sampel deterministik minimal 10% dari include harus diperiksa manusia kedua yang berbeda, lalu kurasi disetujui eksplisit. `package` tetap fail-closed sampai receipt dan approval lengkap. UI bukan classifier dan workflow tidak menghasilkan box.

Aset dan manifest generated berada di `datasets/raw/banana_bunch_detection/` dan `datasets/processed/banana_bunch_detection/`, yang diabaikan Git. Lolos audit hanya menghasilkan `DATASET_READY_FOR_REVIEW`; training detector tetap langkah terpisah.

## Batasan

- Performa model tabular berasal dari data sintetis dan tidak boleh digunakan sebagai klaim produksi; dataset longitudinal asli tetap diperlukan.
- Baseline CV dilatih pada foto terkontrol dari satu dataset. Metrik tinggi pada grouped test tidak membuktikan generalisasi ke kamera, kebun, pencahayaan, background, atau pisang di luar distribusi tersebut.
- Kelas CV bersifat image-level; model belum mendeteksi lokasi pisang dan belum menggabungkan output visual dengan DAF/tabular secara otomatis.
- Artifact Joblib hanya boleh dimuat dari sumber tepercaya karena format pickle dapat mengeksekusi kode saat deserialisasi.
