# PisGo Web

Next.js MVP for Cavendish harvest, route, and arrival-maturity planning.

## Setup

1. Copy the repository environment example into this app:

   ```bash
   cp ../../.env.example .env.local
   ```

2. Set `TOMTOM_API_KEY` (for location suggest, details, and address geocoding), `FOURSQUARE_API_KEY` (for POI search), and `GEOAPIFY_API_KEY` (for routing and map tiles) in `apps/web/.env.local`. Keys stay server-side behind Next.js route handlers.
3. Install and run:

   ```bash
   npm install
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

## MVP boundaries

- TomTom Places Search (Suggest/Discover/Details v3) and Geocoding (v2) handle location autocomplete and geocoding.
- Geoapify light-truck routing and raster map tiles are live when `GEOAPIFY_API_KEY` is configured.
- `lib/prediction/mock.ts` follows the shared prediction response contract but does not inspect image pixels.
- `lib/optimizer/baseline.ts` is a replaceable scheduling heuristic, not a validated maturity forecast.
- Replace the export in `lib/prediction/index.ts` when the versioned AI service is ready.
