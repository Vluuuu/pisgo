import type { Coordinates, RouteData, RoutingVehicleMode } from "../../types/location.ts";
import { DEFAULT_ROUTING_VEHICLE_MODE } from "../../types/location.ts";
import { getGeoapifyApiKey } from "./config.ts";

export const ALLOWED_ROUTING_VEHICLE_MODES = new Set<RoutingVehicleMode>([
  "motorcycle",
  "light_truck",
  "medium_truck",
  "truck",
  "heavy_truck",
]);

export function isValidRoutingVehicleMode(mode: unknown): mode is RoutingVehicleMode {
  return typeof mode === "string" && ALLOWED_ROUTING_VEHICLE_MODES.has(mode as RoutingVehicleMode);
}

export type RoutingErrorCode =
  | "UPSTREAM_TIMEOUT"
  | "UPSTREAM_HTTP_ERROR"
  | "NO_ROUTE"
  | "INVALID_RESPONSE";

export class RoutingError extends Error {
  readonly code: RoutingErrorCode;
  readonly status: number;

  constructor(code: RoutingErrorCode, message: string, status = 502) {
    super(message);
    this.name = "RoutingError";
    this.code = code;
    this.status = status;
  }
}

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
  if (feature?.geometry?.type !== "MultiLineString" || !coordinates?.length || distance === undefined || duration === undefined) {
    throw new RoutingError("NO_ROUTE", "Rute tidak dapat dibuat dari titik ini. Coba pilih titik yang lebih dekat ke jalan yang dapat dilalui kendaraan.");
  }

  const path = coordinates.flatMap((leg) =>
    leg.flatMap((point) => point.length >= 2 ? [[point[1], point[0]] as [number, number]] : []),
  );
  if (path.length < 2) {
    throw new RoutingError("INVALID_RESPONSE", "The route geometry returned by Geoapify is invalid.");
  }

  return { distanceMeters: distance, durationSeconds: duration, path };
}

export async function getRoute(
  origin: Coordinates,
  destination: Coordinates,
  vehicleMode: RoutingVehicleMode = DEFAULT_ROUTING_VEHICLE_MODE,
): Promise<RouteData> {
  const mode = isValidRoutingVehicleMode(vehicleMode) ? vehicleMode : DEFAULT_ROUTING_VEHICLE_MODE;
  const params = new URLSearchParams({
    apiKey: getGeoapifyApiKey(),
    waypoints: `${origin.lat},${origin.lon}|${destination.lat},${destination.lon}`,
    mode,
    units: "metric",
    traffic: "approximated",
    format: "geojson",
  });

  let response: Response;
  try {
    response = await fetch(`https://api.geoapify.com/v1/routing?${params}`, {
      signal: AbortSignal.timeout(15_000),
      cache: "no-store",
    });
  } catch (error) {
    const isTimeout = error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
    if (process.env.NODE_ENV !== "production") {
      console.error("[geoapify/routing] Request network/timeout error:", {
        vehicleMode: mode,
        isTimeout,
        error: error instanceof Error ? error.message : String(error),
      });
    }
    if (isTimeout) {
      throw new RoutingError("UPSTREAM_TIMEOUT", "Route calculation timed out. Please try again.");
    }
    throw new RoutingError("UPSTREAM_HTTP_ERROR", "Could not connect to routing service.");
  }

  if (!response.ok) {
    let upstreamMessage = "";
    try {
      const errBody = (await response.json()) as { message?: string; error?: string };
      upstreamMessage = typeof errBody.message === "string" ? errBody.message : (typeof errBody.error === "string" ? errBody.error : "");
    } catch {
      // Body not JSON or unreadable
    }

    if (process.env.NODE_ENV !== "production") {
      console.error("[geoapify/routing] Upstream error response:", {
        vehicleMode: mode,
        status: response.status,
        statusText: response.statusText,
        upstreamMessage,
      });
    }

    if (response.status === 400 || response.status === 422) {
      throw new RoutingError("NO_ROUTE", "Rute tidak dapat dibuat dari titik ini. Coba pilih titik yang lebih dekat ke jalan yang dapat dilalui kendaraan.");
    }

    throw new RoutingError("UPSTREAM_HTTP_ERROR", "Geoapify could not calculate this route.");
  }

  const data = (await response.json()) as { features?: RoutingFeature[] };
  return parseRoutingResponse(data);
}
