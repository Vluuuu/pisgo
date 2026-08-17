import { getRoute } from "@/lib/geoapify/routing";
import type { Coordinates } from "@/types/location";

function isCoordinates(value: unknown): value is Coordinates {
  if (!value || typeof value !== "object") return false;
  const point = value as Partial<Coordinates>;
  return typeof point.lat === "number" && Number.isFinite(point.lat) && point.lat >= -90 && point.lat <= 90
    && typeof point.lon === "number" && Number.isFinite(point.lon) && point.lon >= -180 && point.lon <= 180;
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as { origin?: unknown; destination?: unknown };
    if (!isCoordinates(body.origin) || !isCoordinates(body.destination)) {
      return Response.json({ error: "Choose valid origin and destination locations." }, { status: 400 });
    }
    if (body.origin.lat === body.destination.lat && body.origin.lon === body.destination.lon) {
      return Response.json({ error: "Origin and destination must be different." }, { status: 400 });
    }

    return Response.json(await getRoute(body.origin, body.destination));
  } catch (error) {
    const message = error instanceof Error ? error.message : "Route calculation failed.";
    return Response.json({ error: message }, { status: 502 });
  }
}
