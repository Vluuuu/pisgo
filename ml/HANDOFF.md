# ML Inference Handoff

Dua baseline kini dapat melakukan inference tanpa training ulang. Output berikut adalah raw output model dan sengaja belum diadaptasi ke kontrak frontend PisGo.

## 1. Computer vision maturity classifier

### Status dan input

Model menerima piksel satu foto dan mengklasifikasikan kematangan Cavendish menjadi:

```text
unripe
half_ripe
ripe
overripe
```

Dataset training: `D:\Augmented Banana Variety Dataset.zip`. Model membaca ZIP secara langsung; gambar tidak diekstrak atau di-commit. Dataset memiliki label tingkat gambar, bukan bounding box, sehingga baseline ini classifier dan bukan YOLO.

Contoh foto input aktual di dalam ZIP:

```text
Augmented Banana Variety Dataset/Cavendish/Cavendish_Ripe_Top_0002.jpg
```

### Format artifact CV

```text
File: models/cavendish_maturity_classifier.joblib
Format: compressed Joblib/Pickle dictionary
artifact_format: pisgo_ml.cv.joblib
artifact_version: 1
model_version: cavendish-color-texture-v1
```

Artifact memuat preprocessing config, feature extractor RGB/HSV/spatial/edge/texture, fitted `StandardScaler`, fitted multinomial `LogisticRegression`, label order, metadata dataset/split, runtime versions, dan metrics. Inference tidak fit atau train ulang.

### Preprocessing CV

1. EXIF orientation transpose.
2. Konversi menjadi RGB.
3. Resize deterministik ke `192 × 128`.
4. Ekstraksi histogram dan summary RGB/HSV.
5. Spatial grid color statistics `3 × 3`.
6. Edge density, saturation, brightness, dan foreground proxy.
7. Scaling menggunakan parameter training yang tersimpan di artifact.

### Cara run CV

Dari folder `ml`:

```powershell
python -m pip install -e ".[dev]"
python -m pisgo_ml.cv_predict --config configs/cv_baseline.yaml `
  --member "Augmented Banana Variety Dataset/Cavendish/Cavendish_Ripe_Top_0002.jpg"
```

Untuk file foto biasa:

```powershell
python -m pisgo_ml.cv_predict --config configs/cv_baseline.yaml --image path/to/photo.jpg
```

Training ulang hanya diperlukan jika dataset/config/model berubah:

```powershell
python -m pisgo_ml.cv_train --config configs/cv_baseline.yaml
```

### Raw output CV aktual, persis tanpa adapter

```json
{
  "artifact_format": "pisgo_ml.cv.joblib",
  "model_version": "cavendish-color-texture-v1",
  "task": "cavendish_maturity_image_classification",
  "variety": "Cavendish",
  "input_reference": "D:\\Augmented Banana Variety Dataset.zip!/Augmented Banana Variety Dataset/Cavendish/Cavendish_Ripe_Top_0002.jpg",
  "predicted_class": "ripe",
  "confidence": 0.99760627,
  "class_probabilities": {
    "unripe": 0.00083948,
    "half_ripe": 0.00060762,
    "ripe": 0.99760627,
    "overripe": 0.00094663
  },
  "preprocessing": {
    "image_mode": "RGB",
    "resize": [192, 128],
    "orientation": "EXIF transpose",
    "features": "RGB/HSV histograms and summaries, spatial grid, edge and pixel ratios"
  },
  "inference_milliseconds": 18.918
}
```

### Split dan batasan CV

Split dilakukan berdasarkan `variety + maturity_class + specimen_id`; semua view dan augmentasi spesimen yang sama berada di split yang sama. Validation/test hanya menggunakan original image. Baseline mendapat accuracy/F1 1.0 pada 52 gambar test dari 13 spesimen, tetapi angka ini **bukan klaim performa lapangan**: dataset sangat terkontrol, kelas memiliki perbedaan warna kuat, dan jumlah spesimen terbatas. Validasi foto dari perangkat/background nyata tetap wajib sebelum integrasi produksi.

## 2. Tabular harvest/arrival predictor

### Format artifact tabular

```text
File: models/cavendish_predictor.joblib
Format: compressed Joblib/Pickle dictionary
artifact_format: pisgo_ml.joblib
artifact_version: 1
model_version: tabular-rf-v1
```

Artifact memuat feature engineering tanggal/agronomi/logistik, imputasi, one-hot encoder, harvest/arrival regressors, readiness classifier, feature names, runtime, dan metrics.

### Cara run tabular

```powershell
python -m pisgo_ml.predict --config configs/default.yaml `
  --input data/sample/cavendish_inference_sample.csv `
  --output reports/predictions.csv
```

### Raw output tabular aktual

```csv
record_id,image_id,plant_id,bunch_id,prediction_reference_date,predicted_harvest_days_from_photo,predicted_harvest_date,predicted_arrival_days_from_photo,predicted_arrival_date,predicted_readiness_status,readiness_confidence,model_version
rec_0001,img_0001.jpg,plant_001,bunch_001,2025-10-24,8,2025-11-01,11,2025-11-04,approaching,0.858333,tabular-rf-v1
```

Data tabular saat ini sintetis, sehingga outputnya hanya untuk menguji pipeline dan kontrak, bukan keputusan agronomi produksi.

## Catatan integrasi

Jangan load Joblib dari browser atau dari sumber tidak tepercaya. Python inference service sebaiknya memuat kedua artifact satu kali ketika service startup. Adapter PisGo dapat mempertahankan raw output CV/tabular untuk debugging lalu mengubahnya ke kontrak frontend secara terpisah. Model CV dan tabular belum digabung otomatis dalam satu ensemble.
