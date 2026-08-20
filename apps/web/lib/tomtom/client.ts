import type { LocationSuggestion } from "@/types/location";
import { getTomTomApiKey } from "./config.ts";
import type {
  LocationSearchSuggestion,
  TomTomAddress,
  TomTomDiscoverItem,
  TomTomDiscoverResponse,
  TomTomFlowLinkage,
  TomTomGeocodeItem,
  TomTomGeocodeResponse,
  TomTomPosition,
  TomTomSuggestItem,
  TomTomSuggestResponse,
} from "./types.ts";

const ID_COUNTRY_ISO2 = "ID";
const ACCEPT_LANGUAGE_ID = "id-ID,id;q=0.9,en;q=0.8";
const PLACES_BASE_URL = "https://api.tomtom.com/maps/orbis/places";
const ALLOWED_DETAILS_TYPES = new Set(["pois", "addresses", "streets", "intersections", "areas"]);

export const TRUSTED_AREA_TYPES = new Set([
  "municipality",
  "municipalitySubdivision",
  "municipalitySecondarySubdivision",
  "neighborhood",
  "countrySecondarySubdivision",
  "countryTertiarySubdivision",
]);

export function extractCoordinates(position?: TomTomPosition): { lat: number; lon: number } | null {
  const coordinates = position?.coordinates;
  if (!Array.isArray(coordinates) || coordinates.length < 2 || coordinates.length > 3) return null;

  const [lon, lat] = coordinates;
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return null;
  if (lon < -180 || lon > 180) return null;
  if (lat < -90 || lat > 90) return null;

  return { lat, lon };
}

function normalizeAddressLabel(address?: TomTomAddress): string | null {
  if (!address) return null;

  const streetLine = [address.street, address.houseNumber].filter(Boolean).join(" ").trim();
  const parts = [
    streetLine || null,
    address.municipalitySecondarySubdivision,
    address.municipalitySubdivision,
    address.municipality,
    address.countrySubdivision,
    address.country,
  ].filter((part): part is string => Boolean(part && part.trim()));

  if (parts.length === 0) return null;
  return parts.join(", ");
}

function normalizeItemLabel(item: Pick<TomTomSuggestItem, "title" | "subtitles" | "address">): string | null {
  if (item.title?.trim()) return item.title.trim();
  if (item.subtitles?.some((subtitle) => subtitle.trim())) return item.subtitles.map((subtitle) => subtitle.trim()).filter(Boolean).join(", ");
  return normalizeAddressLabel(item.address);
}

function normalizeItemSubtitles(subtitles?: string[]): string | undefined {
  if (!subtitles || !Array.isArray(subtitles)) return undefined;
  const joined = subtitles.map((s) => s.trim()).filter(Boolean).join(", ");
  return joined || undefined;
}

function normalizeResolvedItem(
  item: Pick<TomTomDiscoverItem | TomTomGeocodeItem, "id" | "title" | "subtitles" | "address" | "position">,
  index = 0,
): LocationSuggestion | null {
  const coords = extractCoordinates(item.position);
  if (!coords) return null;

  const label = normalizeItemLabel(item);
  if (!label) return null;

  return {
    id: item.id ?? `tomtom-${index}-${coords.lat}-${coords.lon}`,
    label,
    lat: coords.lat,
    lon: coords.lon,
    city: item.address?.municipality ?? item.address?.municipalitySubdivision,
    state: item.address?.countrySubdivision,
    country: item.address?.country,
    provider: "tomtom",
  };
}

export function normalizeSuggestItem(item: TomTomSuggestItem, index = 0): LocationSearchSuggestion | null {
  const label = normalizeItemLabel(item);
  if (!label) return null;

  // Filter out unsupported discoverAction suggestions for MVP
  if (!item.more || item.more.operation !== "details") {
    return null;
  }

  const id = item.id ?? `suggest-${index}`;
  return {
    status: "pending",
    id,
    label,
    subtitles: normalizeItemSubtitles(item.subtitles),
    more: item.more,
  };
}

export function normalizeDiscoverItem(item: TomTomDiscoverItem, index = 0): LocationSuggestion | null {
  return normalizeResolvedItem(item, index);
}

export function normalizeGeocodeItem(item: TomTomGeocodeItem, index = 0): LocationSuggestion | null {
  return normalizeResolvedItem(item, index);
}

function parseDetailsPathParameters(more: TomTomFlowLinkage): { type: string; id: string } | null {
  if (more.operation !== "details") return null;
  if (!Array.isArray(more.pathParameters)) return null;

  let type = "";
  let id = "";

  for (const pathParameter of more.pathParameters) {
    if (pathParameter.parameter === "type") type = pathParameter.argument ?? "";
    if (pathParameter.parameter === "id") id = pathParameter.argument ?? "";
  }

  if (!type || !id || id.length > 200) return null;
  if (!ALLOWED_DETAILS_TYPES.has(type)) return null;

  return { type, id };
}

const PLACES_SUGGEST_ATTRIBUTES = "results(id,type,title,subtitles,more)";
const PLACES_DISCOVER_ATTRIBUTES = "results(id,type,title,subtitles,position,address)";
const PLACES_DETAILS_ATTRIBUTES = "id,type,title,subtitles,position,address";
const GEOCODE_ATTRIBUTES = "results(id,type,title,position,address)";
const AREA_GEOCODE_ATTRIBUTES = "results(id,type,title,position,address,areaType)";

type TomTomEndpoint = "suggest" | "discover" | "details" | "geocode" | "areaGeocode";

function getAttributes(endpoint: TomTomEndpoint): string {
  switch (endpoint) {
    case "suggest":
      return PLACES_SUGGEST_ATTRIBUTES;
    case "discover":
      return PLACES_DISCOVER_ATTRIBUTES;
    case "details":
      return PLACES_DETAILS_ATTRIBUTES;
    case "geocode":
      return GEOCODE_ATTRIBUTES;
    case "areaGeocode":
      return AREA_GEOCODE_ATTRIBUTES;
  }
}

function buildHeaders(apiKey: string, endpoint: TomTomEndpoint, sessionId?: string): Record<string, string> {
  const headers: Record<string, string> = {
    "TomTom-Api-Key": apiKey,
    "TomTom-Api-Version": endpoint === "geocode" || endpoint === "areaGeocode" ? "2" : "3",
    "Attributes": getAttributes(endpoint),
    "Accept-Language": ACCEPT_LANGUAGE_ID,
    "Accept": "application/json",
  };

  if (endpoint === "suggest" || endpoint === "discover") {
    headers["Content-Type"] = "application/json";
  }

  if (endpoint !== "geocode" && endpoint !== "areaGeocode" && sessionId) {
    headers["Session-Id"] = sessionId;
  }

  return headers;
}

async function fetchJson<T>(url: string, init: RequestInit, errorLabel: string): Promise<T> {
  const response = await fetch(url, {
    ...init,
    signal: AbortSignal.timeout(10_000),
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`${errorLabel} failed with status ${response.status}.`);
  }

  return (await response.json()) as T;
}

export async function fetchTomTomSuggest(
  query: string,
  sessionId?: string,
  maxResults = 6,
): Promise<LocationSearchSuggestion[]> {
  const apiKey = getTomTomApiKey();
  const data = await fetchJson<TomTomSuggestResponse>(
    `${PLACES_BASE_URL}/suggest`,
    {
      method: "POST",
      headers: buildHeaders(apiKey, "suggest", sessionId),
      body: JSON.stringify({
        query,
        maxResults,
        filters: {
          countryCodesIso2: [ID_COUNTRY_ISO2],
        },
      }),
    },
    "TomTom suggest request",
  );

  return (data.results ?? [])
    .map((item, index) => normalizeSuggestItem(item, index))
    .filter((item): item is LocationSearchSuggestion => item !== null);
}

export async function fetchTomTomDiscover(
  query: string,
  sessionId?: string,
  maxResults = 6,
): Promise<LocationSuggestion[]> {
  const apiKey = getTomTomApiKey();
  const data = await fetchJson<TomTomDiscoverResponse>(
    `${PLACES_BASE_URL}/discover`,
    {
      method: "POST",
      headers: buildHeaders(apiKey, "discover", sessionId),
      body: JSON.stringify({
        query,
        maxResults,
        filters: {
          countryCodesIso2: [ID_COUNTRY_ISO2],
        },
      }),
    },
    "TomTom discover request",
  );

  return (data.results ?? [])
    .map((item, index) => normalizeDiscoverItem(item, index))
    .filter((item): item is LocationSuggestion => item !== null);
}

export async function fetchTomTomGeocode(
  query: string,
  maxResults = 6,
): Promise<LocationSuggestion[]> {
  const apiKey = getTomTomApiKey();
  const params = new URLSearchParams({
    query,
    maxResults: String(maxResults),
    countryCodesIso2: ID_COUNTRY_ISO2,
  });

  const data = await fetchJson<TomTomGeocodeResponse>(
    `${PLACES_BASE_URL}/geocode?${params.toString()}`,
    {
      method: "GET",
      headers: buildHeaders(apiKey, "geocode"),
    },
    "TomTom geocode request",
  );

  return (data.results ?? [])
    .map((item, index) => normalizeGeocodeItem(item, index))
    .filter((item): item is LocationSuggestion => item !== null);
}

export async function fetchTomTomAreaGeocode(
  query: string,
  maxResults = 1,
): Promise<TomTomGeocodeItem[]> {
  const apiKey = getTomTomApiKey();
  const params = new URLSearchParams({
    query,
    maxResults: String(maxResults),
    countryCodesIso2: ID_COUNTRY_ISO2,
    types: "area",
  });

  const data = await fetchJson<TomTomGeocodeResponse>(
    `${PLACES_BASE_URL}/geocode?${params.toString()}`,
    {
      method: "GET",
      headers: buildHeaders(apiKey, "areaGeocode"),
    },
    "TomTom area geocode request",
  );

  return data.results ?? [];
}

export async function fetchTomTomDetailsByMore(
  more: TomTomFlowLinkage,
  sessionId?: string,
): Promise<LocationSuggestion | null> {
  const parsed = parseDetailsPathParameters(more);
  if (!parsed) return null;

  const apiKey = getTomTomApiKey();
  const data = await fetchJson<TomTomDiscoverItem>(
    `${PLACES_BASE_URL}/details/${parsed.type}/${encodeURIComponent(parsed.id)}`,
    {
      method: "GET",
      headers: buildHeaders(apiKey, "details", sessionId),
    },
    "TomTom details request",
  );

  return normalizeDiscoverItem(data);
}
