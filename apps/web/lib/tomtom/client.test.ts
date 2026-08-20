import assert from "node:assert/strict";
import test from "node:test";
import {
  extractCoordinates,
  fetchTomTomAreaGeocode,
  fetchTomTomDetailsByMore,
  fetchTomTomSuggest,
  normalizeDiscoverItem,
  normalizeGeocodeItem,
  normalizeSuggestItem,
} from "./client.ts";

test("normalizeSuggestItem creates pending suggestion with subtitles and ignores fake coordinates", () => {
  const item = {
    id: "Xyfi123",
    type: "poi",
    title: "Sman 79",
    poiTypes: [{ id: "school", name: "School" }],
    subtitles: [
      "Jalan Kebon Pala 2 26",
      "Kelurahan Tanah Abang, Kecamatan Jakarta",
      "Jakarta 10230",
    ],
    more: {
      operation: "details",
      pathParameters: [
        { parameter: "type", argument: "pois" },
        { parameter: "id", argument: "Xyfi123" },
      ],
    },
  };

  const normalized = normalizeSuggestItem(item);
  assert.ok(normalized);
  assert.equal(normalized.status, "pending");
  assert.equal(normalized.id, "Xyfi123");
  assert.equal(normalized.label, "Sman 79");
  assert.equal(
    normalized.subtitles,
    "Jalan Kebon Pala 2 26, Kelurahan Tanah Abang, Kecamatan Jakarta, Jakarta 10230",
  );
  assert.deepEqual(normalized.more, item.more);
  // Ensure no coordinates exist on pending suggest
  assert.equal("lat" in normalized, false);
  assert.equal("lon" in normalized, false);
});

test("normalizeSuggestItem filters out unsupported discover operations", () => {
  const item = {
    id: "Xyfi-discover",
    type: "poi",
    title: "Sman 79",
    more: {
      operation: "discover",
      pathParameters: [
        { parameter: "type", argument: "pois" },
        { parameter: "id", argument: "Xyfi-discover" },
      ],
    },
  };

  const normalized = normalizeSuggestItem(item);
  assert.equal(normalized, null);
});

test("extractCoordinates accepts 2-element and 3-element coordinates [lon, lat, ele]", () => {
  const coords2D = extractCoordinates({
    type: "Point",
    coordinates: [106.8382, -6.22],
  });
  assert.ok(coords2D);
  assert.equal(coords2D.lat, -6.22);
  assert.equal(coords2D.lon, 106.8382);

  const coords3D = extractCoordinates({
    type: "Point",
    coordinates: [106.8382, -6.22, 14.5],
  });
  assert.ok(coords3D);
  assert.equal(coords3D.lat, -6.22);
  assert.equal(coords3D.lon, 106.8382);

  assert.equal(extractCoordinates({ type: "Point", coordinates: [106.8382] }), null);
  assert.equal(extractCoordinates({ type: "Point", coordinates: [106.8382, -6.22, 14.5, 99.9] }), null);
});

test("normalizeDiscoverItem normalizes GeoJSON point [lon, lat] correctly", () => {
  const item = {
    id: "poi-79",
    type: "poi",
    title: "SMA Negeri 79 Jakarta",
    position: {
      type: "Point" as const,
      coordinates: [106.8382, -6.22],
    },
    subtitles: ["Jl. Menteng Pulo No.19, Jakarta Selatan"],
    address: {
      country: "Indonesia",
      countryCodeIso2: "ID",
      municipality: "Jakarta Selatan",
      countrySubdivision: "DKI Jakarta",
      street: "Jl. Menteng Pulo",
      houseNumber: "19",
    },
  };

  const normalized = normalizeDiscoverItem(item);
  assert.ok(normalized);
  assert.equal(normalized.id, "poi-79");
  assert.equal(normalized.label, "SMA Negeri 79 Jakarta");
  assert.equal(normalized.lat, -6.22);
  assert.equal(normalized.lon, 106.8382);
  assert.equal(normalized.city, "Jakarta Selatan");
  assert.equal(normalized.state, "DKI Jakarta");
  assert.equal(normalized.country, "Indonesia");
  assert.equal(normalized.provider, "tomtom");
});

test("normalizeGeocodeItem parses title first and rejects invalid coordinates", () => {
  const item = {
    id: "geo-cikoko",
    type: "address",
    title: "Jalan Cikoko Timur 42, Pancoran, Jakarta Selatan",
    position: {
      type: "Point" as const,
      coordinates: [106.857, -6.245],
    },
    address: {
      street: "Jalan Cikoko Timur",
      houseNumber: "42",
      municipality: "Jakarta Selatan",
      countrySubdivision: "DKI Jakarta",
      country: "Indonesia",
    },
  };

  const normalized = normalizeGeocodeItem(item);
  assert.ok(normalized);
  assert.equal(normalized.label, "Jalan Cikoko Timur 42, Pancoran, Jakarta Selatan");
  assert.equal(normalized.lat, -6.245);
  assert.equal(normalized.lon, 106.857);
  // Missing "III" from query is never fabricated
  assert.ok(!normalized.label.includes("Timur III"));

  const invalidCoords = {
    id: "geo-bad",
    type: "address",
    title: "Bad Coords",
    position: {
      type: "Point" as const,
      coordinates: [200, -6.245], // Out of range longitude
    },
  };
  assert.equal(normalizeGeocodeItem(invalidCoords), null);
});

test("fetchTomTomSuggest sends TomTom-Api-Key in HEADER, maxResults, and filters.countryCodesIso2", async () => {
  const originalFetch = globalThis.fetch;
  const originalApiKey = process.env.TOMTOM_API_KEY;
  let requestedUrl = "";
  let requestedHeaders: Record<string, string> = {};
  let requestedBody = "";

  process.env.TOMTOM_API_KEY = "test-secret-tomtom-key";

  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    requestedUrl = typeof input === "string" ? input : input.toString();
    requestedHeaders = (init?.headers as Record<string, string>) ?? {};
    requestedBody = typeof init?.body === "string" ? init.body : "";

    return {
      ok: true,
      json: async () => ({
        results: [
          {
            id: "Xyfi123",
            type: "poi",
            title: "Sman 79",
            more: {
              operation: "details",
              pathParameters: [
                { parameter: "type", argument: "pois" },
                { parameter: "id", argument: "Xyfi123" },
              ],
            },
          },
        ],
      }),
    } as unknown as Response;
  }) as typeof fetch;

  try {
    const sessionId = "d7c88b90-1234-4567-89ab-cdef01234567";
    const suggestions = await fetchTomTomSuggest("SMAN 79", sessionId, 5);

    const url = new URL(requestedUrl);
    assert.equal(url.pathname, "/maps/orbis/places/suggest");
    assert.equal(url.searchParams.get("key"), null); // Must NOT put key in query param

    assert.equal(requestedHeaders["TomTom-Api-Key"], "test-secret-tomtom-key");
    assert.equal(requestedHeaders["TomTom-Api-Version"], "3");
    assert.equal(requestedHeaders["Attributes"], "results(id,type,title,subtitles,more)");
    assert.equal(requestedHeaders["Session-Id"], sessionId);

    const body = JSON.parse(requestedBody) as { query: string; maxResults: number; filters?: { countryCodesIso2: string[] } };
    assert.equal(body.query, "SMAN 79");
    assert.equal(body.maxResults, 5);
    assert.deepEqual(body.filters?.countryCodesIso2, ["ID"]);

    assert.equal(suggestions.length, 1);
    assert.equal(suggestions[0].status, "pending");
  } finally {
    globalThis.fetch = originalFetch;
    if (originalApiKey === undefined) {
      delete process.env.TOMTOM_API_KEY;
    } else {
      process.env.TOMTOM_API_KEY = originalApiKey;
    }
  }
});

test("fetchTomTomAreaGeocode requests types=area and includes areaType in Attributes", async () => {
  const originalFetch = globalThis.fetch;
  const originalApiKey = process.env.TOMTOM_API_KEY;
  let requestedUrl = "";
  let requestedHeaders: Record<string, string> = {};

  process.env.TOMTOM_API_KEY = "test-secret-tomtom-key";

  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    requestedUrl = typeof input === "string" ? input : input.toString();
    requestedHeaders = (init?.headers as Record<string, string>) ?? {};

    return {
      ok: true,
      json: async () => ({
        results: [
          {
            id: "area-1",
            type: "area",
            areaType: "municipality",
            title: "Bakauheni",
            position: { type: "Point", coordinates: [105.75, -5.865] },
          },
        ],
      }),
    } as unknown as Response;
  }) as typeof fetch;

  try {
    const results = await fetchTomTomAreaGeocode("Bakauheni", 1);
    const url = new URL(requestedUrl);
    assert.equal(url.pathname, "/maps/orbis/places/geocode");
    assert.equal(url.searchParams.get("query"), "Bakauheni");
    assert.equal(url.searchParams.get("types"), "area");
    assert.equal(url.searchParams.get("countryCodesIso2"), "ID");
    assert.equal(requestedHeaders["Attributes"], "results(id,type,title,position,address,areaType)");
    assert.equal(requestedHeaders["TomTom-Api-Version"], "2");

    assert.equal(results.length, 1);
    assert.equal(results[0].type, "area");
    assert.equal(results[0].areaType, "municipality");
  } finally {
    globalThis.fetch = originalFetch;
    if (originalApiKey === undefined) delete process.env.TOMTOM_API_KEY;
    else process.env.TOMTOM_API_KEY = originalApiKey;
  }
});

test("fetchTomTomDetailsByMore encodes id to prevent path traversal", async () => {
  const originalFetch = globalThis.fetch;
  const originalApiKey = process.env.TOMTOM_API_KEY;
  let requestedUrl = "";

  process.env.TOMTOM_API_KEY = "test-secret-tomtom-key";

  globalThis.fetch = (async (input: string | URL | Request) => {
    requestedUrl = typeof input === "string" ? input : input.toString();

    return {
      ok: true,
      json: async () => ({
        id: "Xyfi/123?test=1",
        type: "poi",
        title: "Test Place",
        position: { type: "Point", coordinates: [106.8382, -6.22] },
      }),
    } as unknown as Response;
  }) as typeof fetch;

  try {
    const more = {
      operation: "details",
      pathParameters: [
        { parameter: "type", argument: "pois" },
        { parameter: "id", argument: "Xyfi/123?test=1" },
      ],
    };
    const result = await fetchTomTomDetailsByMore(more);
    assert.ok(result);
    const url = new URL(requestedUrl);
    assert.equal(url.pathname, "/maps/orbis/places/details/pois/Xyfi%2F123%3Ftest%3D1");
  } finally {
    globalThis.fetch = originalFetch;
    if (originalApiKey === undefined) delete process.env.TOMTOM_API_KEY;
    else process.env.TOMTOM_API_KEY = originalApiKey;
  }
});
