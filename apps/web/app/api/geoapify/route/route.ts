import { getRoute, isValidRoutingVehicleMode, RoutingError } from "@/lib/geoapify/routing";
import { DEFAULT_ROUTING_VEHICLE_MODE } from "@/types/location";
import type { Coordinates } from "@/types/location";

function isCoordinates(value: unknown): value is Coordinates {
  if (!value || typeof value !== "object") return false;
  const point = value as Partial<Coordinates>;
  return typeof point.lat === "number" && Number.isFinite(point.lat) && point.lat >= -90 && point.lat <= 90
    && typeof point.lon === "number" && Number.isFinite(point.lon) && point.lon >= -180 && point.lon <= 180;
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as {
      origin?: unknown;
      destination?: unknown;
      vehicleMode?: unknown;
    };
    if (!isCoordinates(body.origin) || !isCoordinates(body.destination)) {
      return Response.json({ error: "Choose valid origin and destination locations." }, { status: 400 });
    }
    if (body.origin.lat === body.destination.lat && body.origin.lon === body.destination.lon) {
      return Response.json({ error: "Origin and destination must be different." }, { status: 400 });
    }

    if (body.vehicleMode !== undefined && !isValidRoutingVehicleMode(body.vehicleMode)) {
      return Response.json({ error: "Invalid vehicle mode." }, { status: 400 });
    }

    const vehicleMode = body.vehicleMode ?? DEFAULT_ROUTING_VEHICLE_MODE;
    return Response.json(await getRoute(body.origin, body.destination, vehicleMode));
  } catch (error) {
    if (error instanceof RoutingError) {
      return Response.json({ error: error.message, code: error.code }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : "Route calculation failed.";
    return Response.json({ error: message }, { status: 502 });
  }
}
