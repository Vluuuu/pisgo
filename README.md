# PisGo 🍌

**Cavendish Banana Harvest & Arrival Predictor**

PisGo adalah sistem berbasis Machine Learning dan Computer Vision untuk membantu menentukan kapan pisang Cavendish sebaiknya dipanen dan dikirim agar tiba di tujuan pada tingkat kematangan yang diinginkan.

## Core idea

```text
Flowering Date
      +
Banana Image
      ↓
Days After Flowering (DAF) + Visual Maturity
      ↓
Current Maturity & Ripening Forecast
      +
Origin / Destination
      ↓
Route Distance & Travel Duration
      ↓
Harvest / Shipping Optimizer
      ↓
Recommended Harvest Date
Recommended Shipping Date
Expected Arrival Maturity
```

## Team split

- **Fullstack / Integration**: web app, backend, Geoapify, database, optimizer, deployment.
- **AI / ML**: dataset preparation, YOLO training, maturity prediction, evaluation, model export.
- **Shared integration**: API contract between the web/backend and AI service.

## Repository structure

```text
pisgo/
├── apps/
│   └── web/                 # Fullstack web application
├── ml/                      # AI/ML training and evaluation
├── services/
│   └── ai-api/              # Model inference service / bridge to web
├── docs/                    # Architecture, API contract, dataset docs
├── shared/
│   └── schemas/             # Shared request/response schemas
├── .env.example
├── .gitignore
└── README.md
```

## Maps & logistics

MVP menggunakan:

- **Geoapify Autocomplete API** — pencarian origin/destination.
- **Geoapify Routing API** — jarak, durasi, dan route geometry.
- **Geoapify Map Tiles + Leaflet** — visualisasi peta dan rute.

## ML experiment

Eksperimen utama membandingkan:

1. **DAF only** → maturity.
2. **Image only** → maturity.
3. **DAF + image** → maturity (proposed model).

## Important repository rule

Dataset gambar, training runs, dan model weights besar **jangan di-commit langsung ke Git biasa**. Simpan dataset di storage eksternal atau gunakan mekanisme artifact/LFS jika benar-benar diperlukan.

## Status

Project initialized for COMPFEST AIC development.
