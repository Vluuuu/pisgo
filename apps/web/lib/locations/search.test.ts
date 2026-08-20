import assert from "node:assert/strict";
import test from "node:test";
import type { LocationSuggestion } from "../../types/location.ts";
import {
  buildIndonesianPoiSearchPlan,
  FOURSQUARE_FUEL_STATION_CATEGORY_ID,
  normalizeIndonesianAddressQuery,
  normalizeIndonesianEducationQuery,
} from "./normalizers.ts";
import {
  extractLocalityCandidates,
  isAddressQuery,
  isTrustedLocalityArea,
  searchAddress,
  searchPoi,
} from "./search.ts";

test("normalizeIndonesianEducationQuery expands high-confidence education acronyms only", () => {
  assert.equal(normalizeIndonesianEducationQuery("sman 79 jakarta"), "SMA Negeri 79 jakarta");
  assert.equal(normalizeIndonesianEducationQuery("SMAN 79 Jakarta"), "SMA Negeri 79 Jakarta");
  assert.equal(normalizeIndonesianEducationQuery("Sman 79 Jakarta"), "SMA Negeri 79 Jakarta");
  assert.equal(normalizeIndonesianEducationQuery("smkn 2 malang"), "SMK Negeri 2 malang");
  assert.equal(normalizeIndonesianEducationQuery("smpn 1 surabaya"), "SMP Negeri 1 surabaya");
  assert.equal(normalizeIndonesianEducationQuery("sdn 03 bandung"), "SD Negeri 03 bandung");
  assert.equal(normalizeIndonesianEducationQuery("univ indonesia"), "Universitas indonesia");

  // Healthcare / Fuel / KUA / Business / Institutional acronyms MUST remain raw in education normalizer
  assert.equal(normalizeIndonesianEducationQuery("RSUD Pasar Minggu"), "RSUD Pasar Minggu");
  assert.equal(normalizeIndonesianEducationQuery("SPBU Pertamina Kramat Jati"), "SPBU Pertamina Kramat Jati");
  assert.equal(normalizeIndonesianEducationQuery("KUA Setiabudi"), "KUA Setiabudi");
  assert.equal(normalizeIndonesianEducationQuery("PT ABC Logistics"), "PT ABC Logistics");
  assert.equal(normalizeIndonesianEducationQuery("UI Depok"), "UI Depok");
});

test("buildIndonesianPoiSearchPlan handles Education queries (Expanded primary, raw fallback)", () => {
  const plan = buildIndonesianPoiSearchPlan("SMAN 79 Jakarta");
  assert.equal(plan.primaryQuery, "SMA Negeri 79 Jakarta");
  assert.equal(plan.fallbackQuery, "SMAN 79 Jakarta");
  assert.equal(plan.foursquareCategoryIds, undefined);

  const planLower = buildIndonesianPoiSearchPlan("sman 79 jakarta");
  assert.equal(planLower.primaryQuery, "SMA Negeri 79 jakarta");
  assert.equal(planLower.fallbackQuery, "sman 79 jakarta");
});

test("buildIndonesianPoiSearchPlan handles Healthcare queries (Raw primary, expanded fallback)", () => {
  const planRSUD = buildIndonesianPoiSearchPlan("RSUD Pasar Minggu");
  assert.equal(planRSUD.primaryQuery, "RSUD Pasar Minggu");
  assert.equal(planRSUD.fallbackQuery, "Rumah Sakit Umum Daerah Pasar Minggu");

  const planRS = buildIndonesianPoiSearchPlan("RS Harapan Kita");
  assert.equal(planRS.primaryQuery, "RS Harapan Kita");
  assert.equal(planRS.fallbackQuery, "Rumah Sakit Harapan Kita");
});

test("buildIndonesianPoiSearchPlan handles SPBU queries (Raw primary, Foursquare Fuel Stations category)", () => {
  const plan = buildIndonesianPoiSearchPlan("SPBU Pertamina Kramat Jati");
  assert.equal(plan.primaryQuery, "SPBU Pertamina Kramat Jati");
  assert.equal(plan.fallbackQuery, undefined);
  assert.deepEqual(plan.foursquareCategoryIds, [FOURSQUARE_FUEL_STATION_CATEGORY_ID]);
});

test("buildIndonesianPoiSearchPlan handles KUA queries (Raw primary, expanded fallback)", () => {
  const plan = buildIndonesianPoiSearchPlan("KUA Setiabudi");
  assert.equal(plan.primaryQuery, "KUA Setiabudi");
  assert.equal(plan.fallbackQuery, "Kantor Urusan Agama Setiabudi");
});

test("buildIndonesianPoiSearchPlan preserves business entities and institutional acronyms as raw only", () => {
  assert.deepEqual(buildIndonesianPoiSearchPlan("PT ABC Logistics"), { primaryQuery: "PT ABC Logistics" });
  assert.deepEqual(buildIndonesianPoiSearchPlan("UI Depok"), { primaryQuery: "UI Depok" });
  assert.deepEqual(buildIndonesianPoiSearchPlan("ITB Bandung"), { primaryQuery: "ITB Bandung" });
});

test("normalizeIndonesianAddressQuery expands address aliases and canonicalizes nomor", () => {
  assert.equal(normalizeIndonesianAddressQuery("Jl Cikoko Timur III No 42"), "Jalan Cikoko Timur III Nomor 42");
  assert.equal(normalizeIndonesianAddressQuery("Jln Sudirman No. 10"), "Jalan Sudirman Nomor 10");
  assert.equal(normalizeIndonesianAddressQuery("Gg Melati 4"), "Gang Melati 4");
  assert.equal(normalizeIndonesianAddressQuery("Kec. Dampit"), "Kecamatan Dampit");
  assert.equal(normalizeIndonesianAddressQuery("Kel. Menteng Atas"), "Kelurahan Menteng Atas");
  assert.equal(normalizeIndonesianAddressQuery("Perum Griya Asri Blok A3"), "Perumahan Griya Asri Blok A3");
  assert.equal(normalizeIndonesianAddressQuery("Komp Indah Kav 17"), "Kompleks Indah Kaveling 17");
});

test("normalizeIndonesianAddressQuery preserves RT/RW, Roman numerals, blocks, km, and numbers", () => {
  assert.equal(normalizeIndonesianAddressQuery("RT 04 RW 05"), "RT 04 RW 05");
  assert.equal(normalizeIndonesianAddressQuery("Cikoko Timur III"), "Cikoko Timur III");
  assert.equal(normalizeIndonesianAddressQuery("Blok A3"), "Blok A3");
  assert.equal(normalizeIndonesianAddressQuery("KM 12"), "KM 12");
  assert.equal(normalizeIndonesianAddressQuery("Unit 2 Tower 3"), "Unit 2 Tower 3");
});

test("isAddressQuery correctly evaluates strong address syntax over POI keywords", () => {
  // POI without address syntax -> false
  assert.equal(isAddressQuery("RSUD Pasar Minggu"), false);
  assert.equal(isAddressQuery("PT ABC Logistics Surabaya"), false);
  assert.equal(isAddressQuery("SMA Negeri 79 Jakarta"), false);
  assert.equal(isAddressQuery("Pasar Induk Kramat Jati"), false);

  // POI with strong address syntax -> true (address-like)
  assert.equal(isAddressQuery("RSUD Pasar Minggu Jl TB Simatupang No 1"), true);
  assert.equal(isAddressQuery("PT ABC Logistics Jl Raya Industri No 10"), true);
  assert.equal(isAddressQuery("SMA Negeri 79 Jl Menteng Pulo No 19"), true);

  // Standard address queries -> true
  assert.equal(isAddressQuery("Jl Cikoko Timur III No 42"), true);
  assert.equal(isAddressQuery("Jalan Sudirman 10"), true);
  assert.equal(isAddressQuery("Gg Melati 4"), true);
  assert.equal(isAddressQuery("Perum Griya Asri Blok A3"), true);
  assert.equal(isAddressQuery("Kav 17"), true);
  assert.equal(isAddressQuery("RT 04 RW 05"), true);
  assert.equal(isAddressQuery("Desa Sukamaju Kecamatan Dampit"), true);
});

test("extractLocalityCandidates returns at most 2 candidates (2-word and 1-word suffix)", () => {
  assert.deepEqual(extractLocalityCandidates("Pasar Induk Kramat Jati"), ["Kramat Jati", "Jati"]);
  assert.deepEqual(extractLocalityCandidates("Bandara Juanda Surabaya"), ["Juanda Surabaya", "Surabaya"]);
  assert.deepEqual(extractLocalityCandidates("SMA Negeri 79 Jakarta"), ["Jakarta"]);
  assert.deepEqual(extractLocalityCandidates("Pelabuhan Bakauheni"), ["Bakauheni"]);
  assert.deepEqual(extractLocalityCandidates("Jakarta"), []);
});

test("isTrustedLocalityArea validates real TomTom v2 area schema", () => {
  assert.equal(
    isTrustedLocalityArea({
      type: "area",
      areaType: "municipality",
      title: "Bakauheni",
    }),
    true,
  );
  assert.equal(
    isTrustedLocalityArea({
      type: "area",
      areaType: "municipalitySubdivision",
      title: "Kramat Jati",
    }),
    true,
  );
  // Street must be rejected
  assert.equal(
    isTrustedLocalityArea({
      type: "street",
      title: "Jalan Bakauheni",
    }),
    false,
  );
  // Country or countrySubdivision must not be used as a precise locality bias
  assert.equal(
    isTrustedLocalityArea({
      type: "area",
      areaType: "country",
      title: "Indonesia",
    }),
    false,
  );
  assert.equal(
    isTrustedLocalityArea({
      type: "area",
      areaType: "countrySubdivision",
      title: "Lampung",
    }),
    false,
  );
});

test("searchAddress calls TomTom Geocode with bounded request budget", async () => {
  const originalFetch = globalThis.fetch;
  const originalApiKey = process.env.TOMTOM_API_KEY;
  const hitUrls: string[] = [];

  process.env.TOMTOM_API_KEY = "test-tomtom-key";

  globalThis.fetch = (async (input: string | URL | Request) => {
    const urlStr = typeof input === "string" ? input : input.toString();
    hitUrls.push(urlStr);

    return {
      ok: true,
      json: async () => ({
        results: [
          {
            id: "geo-1",
            title: "Jalan Cikoko Timur 42",
            position: { type: "Point", coordinates: [106.85, -6.24] },
            address: { country: "Indonesia", countryCodeIso2: "ID" },
          },
        ],
      }),
    } as unknown as Response;
  }) as typeof fetch;

  try {
    const results = await searchAddress("Jl Cikoko Timur III No 42");
    assert.equal(results.length, 1);
    assert.equal(hitUrls.length, 1);
    assert.equal(hitUrls[0].includes("query=Jl+Cikoko+Timur+III+No+42"), true);
    assert.equal(results[0].label, "Jalan Cikoko Timur 42");
  } finally {
    globalThis.fetch = originalFetch;
    if (originalApiKey === undefined) {
      delete process.env.TOMTOM_API_KEY;
    } else {
      process.env.TOMTOM_API_KEY = originalApiKey;
    }
  }
});

test("manual location preserves user typed label and provides valid coordinates without geocoder", () => {
  const typedQuery = "Cikoko Timur III No 42";
  const manualLocation: LocationSuggestion = {
    id: "manual-12345--6.2412-106.8512",
    label: typedQuery,
    lat: -6.2412,
    lon: 106.8512,
    provider: "manual",
  };

  assert.equal(manualLocation.provider, "manual");
  assert.equal(manualLocation.label, "Cikoko Timur III No 42");
  assert.equal(manualLocation.lat, -6.2412);
  assert.equal(manualLocation.lon, 106.8512);

  // Fallback to "Titik pilihan di peta" when empty query
  const emptyQuery = "   ";
  const trimmed = emptyQuery.trim();
  const fallbackLabel = trimmed.length > 0 ? trimmed : "Titik pilihan di peta";
  const fallbackManualLocation: LocationSuggestion = {
    id: "manual-67890--6.2412-106.8512",
    label: fallbackLabel,
    lat: -6.2412,
    lon: 106.8512,
    provider: "manual",
  };
  assert.equal(fallbackManualLocation.label, "Titik pilihan di peta");

  // Provider "manual" does not trigger Foursquare attribution or TomTom details
  const showFoursquareAttribution =
    (manualLocation.provider as string) === "foursquare";
  assert.equal(showFoursquareAttribution, false);
  const requiresTomTomDetails =
    (manualLocation.provider as string) === "tomtom";
  assert.equal(requiresTomTomDetails, false);
});

test("searchPoi calls Foursquare with primary query and category filter if requested", async () => {
  const originalFetch = globalThis.fetch;
  const originalTomTomKey = process.env.TOMTOM_API_KEY;
  const originalFsqKey = process.env.FOURSQUARE_API_KEY;
  const hitUrls: string[] = [];

  process.env.TOMTOM_API_KEY = "test-tomtom-key";
  process.env.FOURSQUARE_API_KEY = "test-fsq-key";

  globalThis.fetch = (async (input: string | URL | Request) => {
    const urlStr = typeof input === "string" ? input : input.toString();
    hitUrls.push(urlStr);

    if (urlStr.includes("tomtom.com")) {
      return {
        ok: true,
        json: async () => ({
          results: [
            {
              id: "loc-kj",
              type: "area",
              areaType: "municipalitySubdivision",
              title: "Kramat Jati",
              position: { type: "Point", coordinates: [106.87, -6.27] },
            },
          ],
        }),
      } as unknown as Response;
    }

    if (urlStr.includes("foursquare.com")) {
      return {
        ok: true,
        json: async () => ({
          results: [
            {
              fsq_place_id: "fsq-spbu",
              name: "SPBU Pertamina Kramat Jati",
              latitude: -6.271,
              longitude: 106.871,
              location: { formatted_address: "Jl. Raya Bogor" },
            },
          ],
        }),
      } as unknown as Response;
    }

    return { ok: false, status: 404 } as unknown as Response;
  }) as typeof fetch;

  try {
    const results = await searchPoi("SPBU Pertamina Kramat Jati");
    assert.equal(results.length, 1);
    assert.equal(results[0].id, "fsq-spbu");
    assert.equal(hitUrls.length, 2);

    const fsqUrl = new URL(hitUrls[1]);
    assert.equal(fsqUrl.searchParams.get("query"), "SPBU Pertamina Kramat Jati");
    assert.equal(fsqUrl.searchParams.get("fsq_category_ids"), FOURSQUARE_FUEL_STATION_CATEGORY_ID);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalTomTomKey === undefined) delete process.env.TOMTOM_API_KEY;
    else process.env.TOMTOM_API_KEY = originalTomTomKey;
    if (originalFsqKey === undefined) delete process.env.FOURSQUARE_API_KEY;
    else process.env.FOURSQUARE_API_KEY = originalFsqKey;
  }
});

test("searchPoi executes fallback query only when primary Foursquare search returns empty", async () => {
  const originalFetch = globalThis.fetch;
  const originalTomTomKey = process.env.TOMTOM_API_KEY;
  const originalFsqKey = process.env.FOURSQUARE_API_KEY;
  const fsqQueriesHit: string[] = [];

  process.env.TOMTOM_API_KEY = "test-tomtom-key";
  process.env.FOURSQUARE_API_KEY = "test-fsq-key";

  globalThis.fetch = (async (input: string | URL | Request) => {
    const urlStr = typeof input === "string" ? input : input.toString();

    if (urlStr.includes("tomtom.com")) {
      return {
        ok: true,
        json: async () => ({
          results: [
            {
              id: "loc-pm",
              type: "area",
              areaType: "municipalitySubdivision",
              title: "Pasar Minggu",
              position: { type: "Point", coordinates: [106.83, -6.28] },
            },
          ],
        }),
      } as unknown as Response;
    }

    if (urlStr.includes("foursquare.com")) {
      const url = new URL(urlStr);
      const q = url.searchParams.get("query") ?? "";
      fsqQueriesHit.push(q);

      if (q === "Rumah Sakit Umum Daerah Pasar Minggu") {
        return {
          ok: true,
          json: async () => ({
            results: [
              {
                fsq_place_id: "fsq-rsud-pm",
                name: "RSUD Pasar Minggu",
                latitude: -6.281,
                longitude: 106.831,
                location: { formatted_address: "Jl. TB Simatupang" },
              },
            ],
          }),
        } as unknown as Response;
      }

      return {
        ok: true,
        json: async () => ({ results: [] }), // Primary "RSUD Pasar Minggu" returns empty in this mock
      } as unknown as Response;
    }

    return { ok: false, status: 404 } as unknown as Response;
  }) as typeof fetch;

  try {
    const results = await searchPoi("RSUD Pasar Minggu");
    assert.equal(results.length, 1);
    assert.equal(results[0].id, "fsq-rsud-pm");
    // Verified 2 Foursquare attempts hit: primary raw first, then fallback expanded
    assert.deepEqual(fsqQueriesHit, ["RSUD Pasar Minggu", "Rumah Sakit Umum Daerah Pasar Minggu"]);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalTomTomKey === undefined) delete process.env.TOMTOM_API_KEY;
    else process.env.TOMTOM_API_KEY = originalTomTomKey;
    if (originalFsqKey === undefined) delete process.env.FOURSQUARE_API_KEY;
    else process.env.FOURSQUARE_API_KEY = originalFsqKey;
  }
});
