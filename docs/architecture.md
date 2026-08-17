# PisGo Architecture

## High-level architecture

```text
                           USER
                            │
          ┌─────────────────┴─────────────────┐
          │                                   │
   Flowering Date                         Banana Image
          │                                   │
          ▼                                   ▼
     DAF Calculator                      AI / YOLO
          │                                   │
          └──────────────┬────────────────────┘
                         ▼
                 Maturity Prediction
                         │
                         ▼
                  Ripening Forecast
                         │
           ┌─────────────┴─────────────┐
           │                           │
      Target Maturity            Origin / Destination
           │                           │
           │                    Geoapify APIs
           │                    - Autocomplete
           │                    - Routing
           │                    - Map Tiles
           │                           │
           └─────────────┬─────────────┘
                         ▼
                     Optimizer
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
         Harvest Date          Shipping Date
              │                     │
              └──────────┬──────────┘
                         ▼
               Expected Arrival Maturity
```

## Service boundaries

### `apps/web`
User-facing application and backend orchestration.

### `ml`
Training, evaluation, datasets metadata, and model export.

### `services/ai-api`
Stable inference boundary between the web/backend and exported ML models.

### `shared/schemas`
Machine-readable contracts shared between teams.

## MVP logistics stack

- Geoapify Autocomplete API
- Geoapify Routing API
- Geoapify Map Tiles
- Leaflet

## Integration principle

Web development must not wait for final model training. The AI endpoint contract is defined early and can be mocked until an exported model is available.
