import type { Coordinates, RouteData } from "@/types/location";
import { getGeoapifyApiKey } from "./config.ts";

type RoutingFeature = {
  geometry?: {
    type?: string;
    coordinates?: number[][][];
  };
  properties?: {
    distance?: number;
    time?: number;
  };
};

export function parseRoutingResponse(data: { features?: RoutingFeature[] }): RouteData {
  const feature = data.features?.[0];
  const distance = feature?.properties?.distance;
  const duration = feature?.properties?.time;
  const coordinates = feature?.geometry?.coordinates;
  if (feature?.geometry?.type !== "MultiLineString" || !coordinates?.length || !distance || !duration) {
    throw new Error("No drivable light-truck route was found between these locations.");
  }

  const path = coordinates.flatMap((leg) =>
    leg.flatMap((point) => point.length >= 2 ? [[point[1], point[0]] as [number, number]] : []),
  );
  if (path.length < 2) throw new Error("The route geometry returned by Geoapify is invalid.");

  return { distanceMeters: distance, durationSeconds: duration, path };
}

export async function getRoute(origin: Coordinates, destination: Coordinates): Promise<RouteData> {
  const params = new URLSearchParams({
    apiKey: getGeoapifyApiKey(),
    waypoints: `${origin.lat},${origin.lon}|${destination.lat},${destination.lon}`,
    mode: "light_truck",
    units: "metric",
    traffic: "approximated",
    format: "geojson",
  });
  const response = await fetch(`https://api.geoapify.com/v1/routing?${params}`, {
    signal: AbortSignal.timeout(15_000),
    cache: "no-store",
  });
  if (!response.ok) throw new Error("Geoapify could not calculate this route.");

  const data = (await response.json()) as { features?: RoutingFeature[] };
  return parseRoutingResponse(data);
}
