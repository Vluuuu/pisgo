import { getGeoapifyApiKey } from "./config.ts";

export type TileStyle = "positron" | "osm-bright";

export const ALLOWED_TILE_STYLES = new Set<string>(["positron", "osm-bright"]);

export function isValidTileStyle(style: unknown): style is TileStyle {
  return typeof style === "string" && ALLOWED_TILE_STYLES.has(style);
}

export function isValidTileCoordinate(
  z: string | number,
  x: string | number,
  y: string | number,
): boolean {
  const zStr = String(z);
  const xStr = String(x);
  const yStr = String(y);

  if (!/^\d+$/.test(zStr) || !/^\d+$/.test(xStr) || !/^\d+$/.test(yStr)) {
    return false;
  }

  const zoom = Number(zStr);
  return zoom >= 0 && zoom <= 20;
}

export function buildTileUrl(
  z: string | number,
  x: string | number,
  y: string | number,
  style: TileStyle = "positron",
): string {
  if (!isValidTileCoordinate(z, x, y)) {
    throw new Error("Invalid tile coordinates.");
  }
  const safeStyle = isValidTileStyle(style) ? style : "positron";
  return `https://maps.geoapify.com/v1/tile/${safeStyle}/${z}/${x}/${y}.png?apiKey=${encodeURIComponent(getGeoapifyApiKey())}`;
}
