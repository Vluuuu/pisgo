import type { LocationSuggestion } from "@/types/location";
import { getGeoapifyApiKey } from "./config";

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

export async function autocompleteLocation(query: string): Promise<LocationSuggestion[]> {
  const params = new URLSearchParams({
    apiKey: getGeoapifyApiKey(),
    text: query,
    format: "json",
    lang: "id",
    limit: "6",
    bias: "proximity:106.8456,-6.2088|countrycode:id",
  });
  const response = await fetch(`https://api.geoapify.com/v1/geocode/autocomplete?${params}`, {
    signal: AbortSignal.timeout(10_000),
    cache: "no-store",
  });
  if (!response.ok) throw new Error("Geoapify autocomplete request failed.");

  const data = (await response.json()) as { results?: GeoapifyResult[] };
  return (data.results ?? []).flatMap((item, index) => {
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
