# PisGo Web

Bagian fullstack aplikasi PisGo.

## Responsibilities

- User interface dan dashboard.
- Input flowering date.
- Upload / camera banana image.
- Origin dan destination autocomplete.
- Geoapify routing integration.
- Leaflet route visualization.
- Backend integration.
- Menampilkan maturity prediction dan rekomendasi harvest/shipping.

## Planned flow

```text
Flowering Date + Banana Photo + Origin + Destination + Target Maturity
                              ↓
                       PisGo Web/Backend
                        ↙            ↘
                 Geoapify API       AI API
                        ↘            ↙
                         Optimizer
                              ↓
                 Harvest / Shipping Result
```

Implementation framework akan ditentukan saat frontend mulai dibuat.
