import assert from "node:assert/strict";
import test from "node:test";
import { getRoute, parseRoutingResponse } from "./routing.ts";

test("getRoute builds Geoapify request with approved parameters", async () => {
  const originalFetch = globalThis.fetch;
  const originalApiKey = process.env.GEOAPIFY_API_KEY;
  let requestedUrl = "";

  process.env.GEOAPIFY_API_KEY = "dummy-test-key";
  globalThis.fetch = (async (input: string | URL | Request) => {
    requestedUrl = typeof input === "string" ? input : input.toString();
    return {
      ok: true,
      json: async () => ({
        features: [
          {
            geometry: {
              type: "MultiLineString",
              coordinates: [
                [
                  [112.634, -7.977],
                  [106.827, -6.175],
                ],
              ],
            },
            properties: {
              distance: 821000,
              time: 67615,
            },
          },
        ],
      }),
    } as unknown as Response;
  }) as typeof fetch;

  try {
    const result = await getRoute({ lat: -7.977, lon: 112.634 }, { lat: -6.175, lon: 106.827 });
    const url = new URL(requestedUrl);

    assert.equal(url.searchParams.get("mode"), "light_truck");
    assert.equal(url.searchParams.get("traffic"), "approximated");
    assert.equal(url.searchParams.get("units"), "metric");
    assert.equal(url.searchParams.get("format"), "geojson");
    assert.equal(url.searchParams.get("waypoints"), "-7.977,112.634|-6.175,106.827");
    assert.equal(result.distanceMeters, 821000);
    assert.equal(result.durationSeconds, 67615);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalApiKey === undefined) {
      delete process.env.GEOAPIFY_API_KEY;
    } else {
      process.env.GEOAPIFY_API_KEY = originalApiKey;
    }
  }
});

test("parseRoutingResponse maps distance, time, and flips coordinates to [lat, lon]", () => {
  const sample = {
    features: [
      {
        geometry: {
          type: "MultiLineString",
          coordinates: [
            [
              [112.634, -7.977],
              [106.827, -6.175],
            ],
          ],
        },
        properties: {
          distance: 821000,
          time: 67615,
        },
      },
    ],
  };

  const parsed = parseRoutingResponse(sample);
  assert.equal(parsed.distanceMeters, 821000);
  assert.equal(parsed.durationSeconds, 67615);
  assert.deepEqual(parsed.path, [
    [-7.977, 112.634],
    [-6.175, 106.827],
  ]);
});

test("parseRoutingResponse throws when properties or geometry are missing or invalid", () => {
  assert.throws(
    () => parseRoutingResponse({}),
    /No drivable light-truck route was found between these locations\./,
  );

  assert.throws(
    () =>
      parseRoutingResponse({
        features: [
          {
            geometry: { type: "LineString", coordinates: [] },
            properties: { distance: 100, time: 10 },
          },
        ],
      }),
    /No drivable light-truck route was found between these locations\./,
  );

  assert.throws(
    () =>
      parseRoutingResponse({
        features: [
          {
            geometry: {
              type: "MultiLineString",
              coordinates: [[[112.634, -7.977]]],
            },
            properties: { distance: 100, time: 10 },
          },
        ],
      }),
    /The route geometry returned by Geoapify is invalid\./,
  );
});
