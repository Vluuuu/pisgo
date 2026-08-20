import type { LocationSuggestion } from "../../types/location.ts";
import { fetchFoursquarePlaces } from "../foursquare/client.ts";
import {
  extractCoordinates,
  fetchTomTomAreaGeocode,
  fetchTomTomDiscover,
  fetchTomTomGeocode,
  TRUSTED_AREA_TYPES,
} from "../tomtom/client.ts";
import type { TomTomGeocodeItem } from "../tomtom/types.ts";
import {
  buildIndonesianPoiSearchPlan,
  normalizeIndonesianAddressQuery,
} from "./normalizers.ts";

export function isAddressQuery(query: string): boolean {
  const normalized = query.trim().toLowerCase();

  // Strong explicit address indicators evaluated FIRST
  const hasStrongAddressSyntax =
    /\b(jl|jln|jalan|gang|gg|blok|kav|kaveling|kavling|rt|rw|perum|perumahan|komp|komplek|kompleks)\b/i.test(normalized) ||
    /\b(?:no|nomor)\b\.?\s*\d+/i.test(normalized) ||
    /\b(?:desa|ds|kelurahan|kel|kecamatan|kec|kabupaten|kab|provinsi|prov)\b/i.test(normalized);

  if (hasStrongAddressSyntax) {
    return true;
  }

  // POI keyword detection
  if (
    /\b(sma|sman|smk|smkn|smp|smpn|sd|sdn|universitas|univ|sekolah|pesantren|institut|politeknik|kampus)\b/i.test(normalized) ||
    /\b(rs|rsud|rsup|puskesmas|klinik|apotek|laboratorium)\b/i.test(normalized) ||
    /\b(spbu|pom bensin|stasiun|terminal|pelabuhan|bandara)\b/i.test(normalized) ||
    /\b(pasar|pasar induk|mall|plaza|supermarket|hypermarket|toko|gudang|pabrik)\b/i.test(normalized) ||
    /\b(masjid|gereja|pura|vihara|klenteng|kua|kantor pos|polres|polsek|samsat|pln|bpn)\b/i.test(normalized) ||
    /\b(hotel|villa|resort|resto|restoran|cafe|kafe|warung)\b/i.test(normalized) ||
    /\b(pt|cv|ud)\b/i.test(normalized)
  ) {
    return false;
  }

  return false;
}

export function extractLocalityCandidates(query: string): string[] {
  const parts = query.trim().split(/\s+/);
  if (parts.length < 2) return [];

  const candidates: string[] = [];

  // 1. Plausible final two-word suffix (if >= 3 tokens total)
  if (parts.length >= 3) {
    const w1 = parts[parts.length - 2];
    const w2 = parts[parts.length - 1];
    const isW1Valid = /^[a-zA-Z]+$/.test(w1) && w1.length >= 3;
    const isW2Valid = /^[a-zA-Z]+$/.test(w2) && w2.length >= 3;
    if (isW1Valid && isW2Valid) {
      candidates.push(`${w1} ${w2}`);
    }
  }

  // 2. Plausible final one-word suffix
  const lastToken = parts[parts.length - 1];
  if (/^[a-zA-Z]+$/.test(lastToken) && lastToken.length >= 4) {
    if (!candidates.includes(lastToken)) {
      candidates.push(lastToken);
    }
  }

  return candidates.slice(0, 2);
}

export function isTrustedLocalityArea(item: TomTomGeocodeItem): boolean {
  if (item.type !== "area") return false;
  if (!item.areaType) return false;
  return TRUSTED_AREA_TYPES.has(item.areaType);
}

export async function searchAddress(query: string): Promise<LocationSuggestion[]> {
  const original = query.trim();
  const normalized = normalizeIndonesianAddressQuery(original);

  // 1. Primary: TomTom Geocode with originalQuery
  try {
    const primaryResults = await fetchTomTomGeocode(original, 6);
    if (primaryResults.length > 0) {
      return primaryResults;
    }
  } catch (error) {
    console.error("[locations] Primary address geocode failed:", error);
  }

  // 2. Fallback: If normalizedQuery differs meaningfully, at most 1 fallback request
  if (normalized && normalized.toLowerCase() !== original.toLowerCase()) {
    try {
      const fallbackResults = await fetchTomTomGeocode(normalized, 6);
      if (fallbackResults.length > 0) {
        return fallbackResults;
      }
    } catch (error) {
      console.error("[locations] Normalized address geocode fallback failed:", error);
    }
  }

  return [];
}

export async function searchPoi(query: string, sessionId?: string): Promise<LocationSuggestion[]> {
  const original = query.trim();
  const plan = buildIndonesianPoiSearchPlan(original);
  const searchTarget = plan.primaryQuery;

  // 1. Attempt max 2 TomTom area locality candidates
  const localityCandidates = extractLocalityCandidates(original);
  let bias: { lat: number; lon: number; radiusMeters: number } | null = null;

  for (const candidate of localityCandidates) {
    try {
      const areaItems = await fetchTomTomAreaGeocode(candidate, 1);
      if (areaItems.length > 0) {
        const first = areaItems[0];
        if (isTrustedLocalityArea(first) && first.position) {
          const coords = extractCoordinates(first.position);
          if (coords) {
            bias = { lat: coords.lat, lon: coords.lon, radiusMeters: 25_000 };
            break; // Stop immediately after the first trustworthy area result
          }
        }
      }
    } catch (error) {
      console.error("[locations] Locality area lookup failed:", error);
    }
  }

  // 2. Execute primary Foursquare search if trustworthy locality exists
  if (bias) {
    try {
      const primaryFsqResults = await fetchFoursquarePlaces(
        searchTarget,
        bias,
        6,
        plan.foursquareCategoryIds,
      );
      if (primaryFsqResults.length > 0) {
        return primaryFsqResults;
      }
    } catch (error) {
      console.error("[locations] Primary Foursquare search failed:", error);
    }

    // 3. Fallback Foursquare search if primary returned empty and fallbackQuery exists
    if (plan.fallbackQuery && plan.fallbackQuery !== searchTarget) {
      try {
        const fallbackFsqResults = await fetchFoursquarePlaces(
          plan.fallbackQuery,
          bias,
          6,
          plan.foursquareCategoryIds,
        );
        if (fallbackFsqResults.length > 0) {
          return fallbackFsqResults;
        }
      } catch (error) {
        console.error("[locations] Fallback Foursquare search failed:", error);
      }
    }
  }

  // 4. Deterministic country-filtered TomTom Discover fallback
  try {
    const discoverResults = await fetchTomTomDiscover(searchTarget, sessionId, 6);
    if (discoverResults.length > 0) {
      return discoverResults;
    }
  } catch (error) {
    console.error("[locations] TomTom Discover fallback failed:", error);
  }

  return [];
}

export async function searchLocationUnified(query: string, sessionId?: string): Promise<LocationSuggestion[]> {
  const trimmed = query.trim();
  if (trimmed.length < 3) return [];

  if (isAddressQuery(trimmed)) {
    return searchAddress(trimmed);
  }

  return searchPoi(trimmed, sessionId);
}
