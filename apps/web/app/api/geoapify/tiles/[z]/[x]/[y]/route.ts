import { getGeoapifyApiKey } from "@/lib/geoapify/config";

type TileParams = Promise<{ z: string; x: string; y: string }>;

export async function GET(_request: Request, { params }: { params: TileParams }) {
  const { z, x, y } = await params;
  if (![z, x, y].every((part) => /^\d+$/.test(part)) || Number(z) > 20) {
    return new Response("Invalid tile coordinates.", { status: 400 });
  }

  try {
    const url = `https://maps.geoapify.com/v1/tile/positron/${z}/${x}/${y}.png?apiKey=${encodeURIComponent(getGeoapifyApiKey())}`;
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
