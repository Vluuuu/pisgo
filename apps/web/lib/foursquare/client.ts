import type { LocationSuggestion } from "@/types/location";
import { getFoursquareApiKey } from "./config.ts";
import type { FoursquarePlace, FoursquareSearchResponse } from "./types.ts";

const FOURSQUARE_SEARCH_URL = "https://places-api.foursquare.com/places/search";
const PLACES_API_VERSION = "2025-06-17";
const REQUESTED_FIELDS = "fsq_place_id,name,latitude,longitude,distance,location";

export function normalizeFoursquarePlace(place: FoursquarePlace, index = 0): LocationSuggestion | null {
  const lat = place.latitude;
  const lon = place.longitude;

  if (typeof lat !== "number" || typeof lon !== "number") return null;
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (lon < -180 || lon > 180 || lat < -90 || lat > 90) return null;

  const name = place.name?.trim();
  if (!name) return null;

  const formattedAddress = place.location?.formatted_address?.trim();
  const label = formattedAddress && formattedAddress !== name
    ? `${name}, ${formattedAddress}`
    : name;

  return {
    id: place.fsq_place_id ?? `fsq-${index}-${lat}-${lon}`,
    label,
    lat,
    lon,
    city: place.location?.locality,
    state: place.location?.region,
    country: place.location?.country,
    provider: "foursquare",
  };
}

export type FoursquareBias = {
  lat: number;
  lon: number;
  radiusMeters?: number;
};

export async function fetchFoursquarePlaces(
  query: string,
  bias: FoursquareBias,
  limit = 6,
  categoryIds?: string[],
): Promise<LocationSuggestion[]> {
  const trimmed = query.trim();
  if (trimmed.length < 3) return [];

  if (!bias || !Number.isFinite(bias.lat) || !Number.isFinite(bias.lon)) {
    throw new Error("Foursquare search requires explicit spatial coordinates to avoid server-IP bias.");
  }

  const apiKey = getFoursquareApiKey();
  const params = new URLSearchParams({
    query: trimmed,
    limit: String(limit),
    sort: "RELEVANCE",
    fields: REQUESTED_FIELDS,
    ll: `${bias.lat},${bias.lon}`,
  });

  if (bias.radiusMeters && bias.radiusMeters > 0) {
    params.set("radius", String(Math.round(bias.radiusMeters)));
  }

  if (categoryIds && categoryIds.length > 0) {
    params.set("fsq_category_ids", categoryIds.join(","));
  }

  const response = await fetch(`${FOURSQUARE_SEARCH_URL}?${params.toString()}`, {
    method: "GET",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "X-Places-Api-Version": PLACES_API_VERSION,
      "Accept": "application/json",
    },
    signal: AbortSignal.timeout(10_000),
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Foursquare places search failed with status ${response.status}.`);
  }

  const data = (await response.json()) as FoursquareSearchResponse;
  return (data.results ?? [])
    .map((item, index) => normalizeFoursquarePlace(item, index))
    .filter((item): item is LocationSuggestion => item !== null);
}
