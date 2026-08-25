# PisGo Architecture

## High-Level System Architecture

```text
                           USER
                            │
          ┌─────────────────┴─────────────────┐
          │                                   │
   Flowering Date + Photo Date            Banana Image
          │                                   │
          ▼                                   ▼
   DAF Biological Age                YOLOv11n Presence Gate
   (Contextual Evidence)                      │
                                              ▼ (if detected)
                                     Cavendish 4-Class CV
                                              │
                                              ▼
                                       Current Maturity
                                       (1–7 UI Scale)
                                              │
          ┌───────────────────────────────────┤
          │                                   │
   Target Maturity                     Travel Duration
   (1–7 Scale)                         (Geoapify Route ETA)
          │                                   │
          └─────────────────┬─────────────────┘
                            ▼
                  PisGO Schedule Optimizer
                  (Baseline Heuristic)
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
         Harvest Date               Shipping Date
              │                           │
              └─────────────┬─────────────┘
                            ▼
                Expected Arrival Maturity
```

## Service Boundaries

### `apps/web`
Fullstack Next.js 16 application. Manages user interactions, form validation, native camera capture, geocoding and routing integration, and orchestrates the schedule optimization workflow.

### `services/ai-api`
FastAPI inference microservice. Enforces the banana presence gate via YOLOv11n, runs 4-class visual maturity inference on detected bunches, maps probabilities to the 1–7 scale, and returns structured, null-safe prediction responses.

### `ml`
Machine learning training, dataset curation, model evaluation, and artifact serialization for both object detection (YOLOv11) and visual classification (Scikit-Learn).

### `shared/schemas`
Machine-readable JSON schema (`prediction.schema.json`) defining the API contract between the web application and the AI service.

## Logistics & Geospatial Stack

- **Geoapify Routing API**: Turn-by-turn road routing, distance calculation, and duration estimation by vehicle mode (`light_truck`, `truck`, `van`, `car`).
- **Geoapify Map Tiles & Leaflet**: Interactive map rendering with route geometry overlays.
- **TomTom Places & Geocoding APIs**: Autocomplete suggestions, address geocoding, and locality resolution.
- **Foursquare Places API**: Categorized point-of-interest (POI) discovery fallback.
