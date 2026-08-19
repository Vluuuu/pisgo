import assert from "node:assert/strict";
import test from "node:test";
import {
  autocompleteLocation,
  cleanIndonesianAddressQuery,
  normalizeGeoapifyResults,
} from "./autocomplete.ts";

test("cleanIndonesianAddressQuery cleans street numbers and abbreviations", () => {
  assert.equal(cleanIndonesianAddressQuery("Jl Cikoko Timur III No 42"), "Jalan Cikoko Timur III");
  assert.equal(cleanIndonesianAddressQuery("Jl. Sudirman Blok A No. 12"), "Jalan Sudirman");
  assert.equal(cleanIndonesianAddressQuery("SMAN 79"), "SMA Negeri 79");
  assert.equal(cleanIndonesianAddressQuery("SMKN 4"), "SMK Negeri 4");
});

test("normalizeGeoapifyResults transforms results into LocationSuggestion shape", () => {
  const normalized = normalizeGeoapifyResults([
    {
      place_id: "place_1",
      formatted: "Jalan Cikoko Timur III, Jakarta Selatan",
      lat: -6.24515,
      lon: 106.85757,
      city: "Jakarta Selatan",
      state: "Jakarta",
      country: "Indonesia",
    },
    {
      address_line1: "Kantor PisGo",
      address_line2: "Jakarta Pusat",
      lat: -6.175,
      lon: 106.827,
    },
  ]);

  assert.equal(normalized.length, 2);
  assert.equal(normalized[0].id, "place_1");
  assert.equal(normalized[0].label, "Jalan Cikoko Timur III, Jakarta Selatan");
  assert.equal(normalized[0].lat, -6.24515);
  assert.equal(normalized[0].lon, 106.85757);
  assert.equal(normalized[1].label, "Kantor PisGo, Jakarta Pusat");
});

test("autocompleteLocation enforces server-side query with filter and fallback", async () => {
  const originalFetch = globalThis.fetch;
  const originalApiKey = process.env.GEOAPIFY_API_KEY;
  const calledUrls: string[] = [];

  process.env.GEOAPIFY_API_KEY = "test-key-never-exposed";

  globalThis.fetch = (async (input: string | URL | Request) => {
    const urlStr = typeof input === "string" ? input : input.toString();
    calledUrls.push(urlStr);

    // If calling autocomplete for detailed address, return 0 results to test search fallback
    if (urlStr.includes("/v1/geocode/autocomplete") && urlStr.includes("Jl+Cikoko+Timur+III+No+42")) {
      return {
        ok: true,
        json: async () => ({ results: [] }),
      } as unknown as Response;
    }

    if (urlStr.includes("/v1/geocode/search") && urlStr.includes("Jl+Cikoko+Timur+III+No+42")) {
      return {
        ok: true,
        json: async () => ({ results: [] }),
      } as unknown as Response;
    }

    if (urlStr.includes("/v1/geocode/search") && urlStr.includes("Jalan+Cikoko+Timur+III")) {
      return {
        ok: true,
        json: async () => ({
          results: [
            {
              place_id: "place_cikoko",
              formatted: "Jalan Cikoko Timur III, Jakarta Selatan 12770, Jawa, Indonesia",
              lat: -6.24515,
              lon: 106.85757,
              city: "Jakarta Selatan",
              state: "Jawa",
              country: "Indonesia",
            },
          ],
        }),
      } as unknown as Response;
    }

    return {
      ok: true,
      json: async () => ({ results: [] }),
    } as unknown as Response;
  }) as typeof fetch;

  try {
    const results = await autocompleteLocation("Jl Cikoko Timur III No 42");
    assert.equal(results.length, 1);
    assert.equal(results[0].id, "place_cikoko");
    assert.equal(results[0].lat, -6.24515);
    // Unresolved house number 42 is not fabricated into label
    assert.equal(results[0].label, "Jalan Cikoko Timur III, Jakarta Selatan 12770, Jawa, Indonesia");
    assert.ok(!results[0].label.includes("42"));

    // Verify all outbound requests included required country filter and server key, without hardcoded bias
    assert.ok(calledUrls.length >= 2);
    for (const urlStr of calledUrls) {
      const url = new URL(urlStr);
      assert.equal(url.searchParams.get("apiKey"), "test-key-never-exposed");
      assert.equal(url.searchParams.get("filter"), "countrycode:id");
      assert.equal(url.searchParams.get("lang"), "id");
      assert.equal(url.searchParams.get("bias"), null);
    }
  } finally {
    globalThis.fetch = originalFetch;
    if (originalApiKey === undefined) {
      delete process.env.GEOAPIFY_API_KEY;
    } else {
      process.env.GEOAPIFY_API_KEY = originalApiKey;
    }
  }
});
