import { buildTileUrl, isValidTileCoordinate, isValidTileStyle } from "@/lib/geoapify/tiles";
import type { TileStyle } from "@/lib/geoapify/tiles";

type TileParams = Promise<{ z: string; x: string; y: string }>;

export async function GET(request: Request, { params }: { params: TileParams }) {
  const { z, x, y } = await params;
  if (!isValidTileCoordinate(z, x, y)) {
    return new Response("Invalid tile coordinates.", { status: 400 });
  }

  const { searchParams } = new URL(request.url);
  const requestedStyle = searchParams.get("style");
  const style: TileStyle = isValidTileStyle(requestedStyle) ? requestedStyle : "positron";

  try {
    const url = buildTileUrl(z, x, y, style);
    const response = await fetch(url, { next: { revalidate: 86_400 } });
    if (!response.ok || !response.body) return new Response("Map tile unavailable.", { status: 502 });
    return new Response(response.body, {
      headers: {
        "Content-Type": response.headers.get("Content-Type") ?? "image/png",
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
      },
    });
  } catch {
    return new Response("Map tile unavailable.", { status: 502 });
  }
}