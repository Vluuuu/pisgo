import assert from "node:assert/strict";
import test from "node:test";
import {
  ALLOWED_TILE_STYLES,
  buildTileUrl,
  isValidTileCoordinate,
  isValidTileStyle,
} from "./tiles.ts";

test("isValidTileStyle validates supported styles and rejects unknown ones", () => {
  assert.equal(isValidTileStyle("positron"), true);
  assert.equal(isValidTileStyle("osm-bright"), true);
  assert.equal(isValidTileStyle("dark-matter"), false);
  assert.equal(isValidTileStyle(""), false);
  assert.equal(isValidTileStyle(null), false);
  assert.equal(isValidTileStyle(undefined), false);
  assert.deepEqual(Array.from(ALLOWED_TILE_STYLES), ["positron", "osm-bright"]);
});

test("isValidTileCoordinate validates integer coordinate format and zoom bounds 0-20", () => {
  // Valid
  assert.equal(isValidTileCoordinate(0, 0, 0), true);
  assert.equal(isValidTileCoordinate("10", "512", "340"), true);
  assert.equal(isValidTileCoordinate(20, 1000, 2000), true);

  // Invalid zoom
  assert.equal(isValidTileCoordinate(21, 0, 0), false);
  assert.equal(isValidTileCoordinate("-1", 0, 0), false);

  // Invalid characters / decimals / strings
  assert.equal(isValidTileCoordinate("10.5", 0, 0), false);
  assert.equal(isValidTileCoordinate("abc", 0, 0), false);
  assert.equal(isValidTileCoordinate(10, "x", 0), false);
  assert.equal(isValidTileCoordinate(10, 0, "y"), false);
  assert.equal(isValidTileCoordinate("", 0, 0), false);
});

test("buildTileUrl constructs proper Geoapify tile URL with default and custom styles", () => {
  const originalApiKey = process.env.GEOAPIFY_API_KEY;
  process.env.GEOAPIFY_API_KEY = "test-geoapify-key";

  try {
    const defaultUrlStr = buildTileUrl(12, 2048, 1024);
    const defaultUrl = new URL(defaultUrlStr);
    assert.equal(defaultUrl.hostname, "maps.geoapify.com");
    assert.equal(defaultUrl.pathname, "/v1/tile/positron/12/2048/1024.png");
    assert.equal(defaultUrl.searchParams.get("apiKey"), "test-geoapify-key");

    const osmUrlStr = buildTileUrl(8, 120, 90, "osm-bright");
    const osmUrl = new URL(osmUrlStr);
    assert.equal(osmUrl.pathname, "/v1/tile/osm-bright/8/120/90.png");

    assert.throws(
      () => buildTileUrl(25, 0, 0),
      /Invalid tile coordinates\./,
    );
  } finally {
    if (originalApiKey === undefined) {
      delete process.env.GEOAPIFY_API_KEY;
    } else {
      process.env.GEOAPIFY_API_KEY = originalApiKey;
    }
  }
});