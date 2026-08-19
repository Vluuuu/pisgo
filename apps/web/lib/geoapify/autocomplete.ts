import type { LocationSuggestion } from "../../types/location.ts";
import { getGeoapifyApiKey } from "./config.ts";

type GeoapifyResult = {
  place_id?: string;
  formatted?: string;
  address_line1?: string;
  address_line2?: string;
  lat?: number;
  lon?: number;
  city?: string;
  state?: string;
  country?: string;
};

const COUNTRY_FILTER = "countrycode:id";

export function normalizeGeoapifyResults(results?: GeoapifyResult[]): LocationSuggestion[] {
  if (!results || !Array.isArray(results)) return [];
  return results.flatMap((item, index) => {
    if (!Number.isFinite(item.lat) || !Number.isFinite(item.lon)) return [];
    const label = item.formatted ?? [item.address_line1, item.address_line2].filter(Boolean).join(", ");
    if (!label) return [];
    return [{
      id: item.place_id ?? `${item.lat}-${item.lon}-${index}`,
      label,
      lat: item.lat as number,
      lon: item.lon as number,
      city: item.city,
      state: item.state,
      country: item.country,
    }];
  });
}

export function cleanIndonesianAddressQuery(query: string): string {
  return query
    .replace(/\b(?:no|nomor|blok|rt|rw)\.?\s*[\w\d/-]+/gi, "")
    .replace(/\bjl\.?(?=\s|$)/gi, "Jalan")
    .replace(/\bSMAN\b/gi, "SMA Negeri")
    .replace(/\bSMKN\b/gi, "SMK Negeri")
    .replace(/\s+/g, " ")
    .trim();
}

function mergeSuggestions(...groups: LocationSuggestion[][]): LocationSuggestion[] {
  const merged = new Map<string, LocationSuggestion>();
  for (const suggestion of groups.flat()) {
    const key = suggestion.id || `${suggestion.lat},${suggestion.lon}`;
    if (!merged.has(key)) merged.set(key, suggestion);
  }
  return [...merged.values()].slice(0, 6);
}

export async function fetchGeoapifyEndpoint(
  endpoint: "autocomplete" | "search",
  query: string,
  apiKey: string,
  limit = 6,
): Promise<GeoapifyResult[]> {
  const params = new URLSearchParams({
    apiKey,
    text: query,
    format: "json",
    lang: "id",
    limit: String(limit),
    filter: COUNTRY_FILTER,
  });
  const response = await fetch(`https://api.geoapify.com/v1/geocode/${endpoint}?${params}`, {
    signal: AbortSignal.timeout(10_000),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Geoapify ${endpoint} request failed.`);
  }

  const data = (await response.json()) as { results?: GeoapifyResult[] };
  return data.results ?? [];
}

export async function autocompleteLocation(query: string): Promise<LocationSuggestion[]> {
  const trimmed = query.trim();
  if (trimmed.length < 3) return [];
  const apiKey = getGeoapifyApiKey();
  const autocomplete = normalizeGeoapifyResults(await fetchGeoapifyEndpoint("autocomplete", trimmed, apiKey));
  if (autocomplete.length >= 6) return autocomplete;

  const search = normalizeGeoapifyResults(await fetchGeoapifyEndpoint("search", trimmed, apiKey, 6 - autocomplete.length));
  let results = mergeSuggestions(autocomplete, search);
  if (results.length >= 6) return results;

  const cleaned = cleanIndonesianAddressQuery(trimmed);
  if (cleaned !== trimmed && cleaned.length >= 3) {
    const cleanedSearch = normalizeGeoapifyResults(await fetchGeoapifyEndpoint("search", cleaned, apiKey, 6 - results.length));
    results = mergeSuggestions(results, cleanedSearch);
  }

  return results;
}
