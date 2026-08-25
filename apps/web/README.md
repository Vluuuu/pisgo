# PisGO Web

Next.js 16 fullstack application for Cavendish harvest, route, and arrival-maturity planning.

## Setup

1. Copy the repository environment example into this app:

   ```bash
   cp ../../.env.example .env.local
   ```

2. Configure environment variables in `apps/web/.env.local`:
   * `GEOAPIFY_API_KEY`: Required for logistics road routing, distance, and duration/ETA.
   * `TOMTOM_API_KEY`: Required for location autocomplete search and geocoding.
   * `FOURSQUARE_API_KEY`: Optional fallback for categorized POI search.
   * `AI_API_BASE_URL`: Required (points to FastAPI inference service, e.g., `http://127.0.0.1:8001`).

3. Install and run:

   ```bash
   npm ci
   npm run dev
   ```

4. Open `http://localhost:3000`.

## Verification

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

## MVP Implementation Notes

- Location autocomplete and search uses TomTom v3/v2 with optional Foursquare POI fallback.
- Logistics routing uses Geoapify vehicle-specific routing (default: `light_truck`) and Leaflet map tiles.
- `lib/prediction/ai-api.ts` connects directly to the FastAPI inference service (`/v1/predict`) implementing the YOLO presence gate + visual maturity response contract.
- `lib/optimizer/baseline.ts` provides a baseline schedule optimizer based on visual maturity, target maturity, travel duration, and photo date.
