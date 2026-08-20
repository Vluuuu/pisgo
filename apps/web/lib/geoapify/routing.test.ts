import assert from "node:assert/strict";
import test from "node:test";
import { getRoute, isValidRoutingVehicleMode, parseRoutingResponse, RoutingError } from "./routing.ts";
import { DEFAULT_ROUTING_VEHICLE_MODE } from "../../types/location.ts";
import type { RoutingVehicleMode } from "../../types/location.ts";

test("DEFAULT_ROUTING_VEHICLE_MODE is light_truck", () => {
  assert.equal(DEFAULT_ROUTING_VEHICLE_MODE, "light_truck");
});

test("isValidRoutingVehicleMode validates allowed modes and rejects arbitrary strings", () => {
  const allowed: RoutingVehicleMode[] = [
    "motorcycle",
    "light_truck",
    "medium_truck",
    "truck",
    "heavy_truck",
  ];
  for (const mode of allowed) {
    assert.equal(isValidRoutingVehicleMode(mode), true);
  }

  assert.equal(isValidRoutingVehicleMode("car"), false);
  assert.equal(isValidRoutingVehicleMode("bicycle"), false);
  assert.equal(isValidRoutingVehicleMode("bus"), false);
  assert.equal(isValidRoutingVehicleMode("walk"), false);
  assert.equal(isValidRoutingVehicleMode("scooter"), false);
  assert.equal(isValidRoutingVehicleMode(""), false);
  assert.equal(isValidRoutingVehicleMode(null), false);
  assert.equal(isValidRoutingVehicleMode(undefined), false);
});

test("getRoute builds Geoapify request with approved parameters and defaults to light_truck", async () => {
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

test("getRoute sends the selected vehicle mode to Geoapify", async () => {
  const originalFetch = globalThis.fetch;
  const originalApiKey = process.env.GEOAPIFY_API_KEY;
  const modesTested: string[] = [];
  const trafficParamTested: string[] = [];

  process.env.GEOAPIFY_API_KEY = "dummy-test-key";
  globalThis.fetch = (async (input: string | URL | Request) => {
    const requestedUrl = typeof input === "string" ? input : input.toString();
    const url = new URL(requestedUrl);
    modesTested.push(url.searchParams.get("mode") ?? "");
    trafficParamTested.push(url.searchParams.get("traffic") ?? "");
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
    const modes: RoutingVehicleMode[] = [
      "motorcycle",
      "light_truck",
      "medium_truck",
      "truck",
      "heavy_truck",
    ];
    for (const mode of modes) {
      await getRoute({ lat: -7.977, lon: 112.634 }, { lat: -6.175, lon: 106.827 }, mode);
    }
    assert.deepEqual(modesTested, modes);
    assert.deepEqual(trafficParamTested, ["approximated", "approximated", "approximated", "approximated", "approximated"]);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalApiKey === undefined) {
      delete process.env.GEOAPIFY_API_KEY;
    } else {
      process.env.GEOAPIFY_API_KEY = originalApiKey;
    }
  }
});

test("getRoute throws UPSTREAM_TIMEOUT on request timeout", async () => {
  const originalFetch = globalThis.fetch;
  const originalApiKey = process.env.GEOAPIFY_API_KEY;

  process.env.GEOAPIFY_API_KEY = "dummy-test-key";
  globalThis.fetch = (async () => {
    const timeoutErr = new Error("The operation was aborted due to timeout");
    timeoutErr.name = "TimeoutError";
    throw timeoutErr;
  }) as typeof fetch;

  try {
    await assert.rejects(
      async () => getRoute({ lat: -7.977, lon: 112.634 }, { lat: -6.175, lon: 106.827 }),
      (err: unknown) => {
        assert.ok(err instanceof RoutingError);
        assert.equal(err.code, "UPSTREAM_TIMEOUT");
        assert.equal(err.status, 502);
        return true;
      },
    );
  } finally {
    globalThis.fetch = originalFetch;
    if (originalApiKey === undefined) {
      delete process.env.GEOAPIFY_API_KEY;
    } else {
      process.env.GEOAPIFY_API_KEY = originalApiKey;
    }
  }
});

test("getRoute throws NO_ROUTE when Geoapify returns 400 bad request", async () => {
  const originalFetch = globalThis.fetch;
  const originalApiKey = process.env.GEOAPIFY_API_KEY;

  process.env.GEOAPIFY_API_KEY = "dummy-test-key";
  globalThis.fetch = (async () => ({
    ok: false,
    status: 400,
    statusText: "Bad Request",
    json: async () => ({
      statusCode: 400,
      error: "Bad Request",
      message: "No suitable edges near location.",
    }),
  })) as unknown as typeof fetch;

  try {
    await assert.rejects(
      async () => getRoute({ lat: -7.977, lon: 112.634 }, { lat: -6.175, lon: 106.827 }),
      (err: unknown) => {
        assert.ok(err instanceof RoutingError);
        assert.equal(err.code, "NO_ROUTE");
        return true;
      },
    );
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

test("parseRoutingResponse throws updated message when properties or geometry are missing or invalid", () => {
  assert.throws(
    () => parseRoutingResponse({}),
    (err: unknown) => {
      assert.ok(err instanceof RoutingError);
      assert.equal(err.code, "NO_ROUTE");
      return /Rute tidak dapat dibuat dari titik ini\. Coba pilih titik yang lebih dekat ke jalan yang dapat dilalui kendaraan\./.test(err.message);
    },
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
    (err: unknown) => {
      assert.ok(err instanceof RoutingError);
      assert.equal(err.code, "NO_ROUTE");
      return /Rute tidak dapat dibuat dari titik ini\. Coba pilih titik yang lebih dekat ke jalan yang dapat dilalui kendaraan\./.test(err.message);
    },
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
    (err: unknown) => {
      assert.ok(err instanceof RoutingError);
      assert.equal(err.code, "INVALID_RESPONSE");
      return /The route geometry returned by Geoapify is invalid\./.test(err.message);
    },
  );
});
