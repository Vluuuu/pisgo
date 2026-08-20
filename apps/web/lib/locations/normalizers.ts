export const FOURSQUARE_FUEL_STATION_CATEGORY_ID = "4bf58dd8d48988d113951735";

export type PoiSearchPlan = {
  primaryQuery: string;
  fallbackQuery?: string;
  foursquareCategoryIds?: string[];
};

export function normalizeIndonesianEducationQuery(query: string): string {
  const trimmed = query.trim().replace(/\s+/g, " ");
  if (!trimmed) return "";

  return trimmed
    .replace(/\bSMAN\b/gi, "SMA Negeri")
    .replace(/\bSMKN\b/gi, "SMK Negeri")
    .replace(/\bSMPN\b/gi, "SMP Negeri")
    .replace(/\bSDN\b/gi, "SD Negeri")
    .replace(/\bUniv\b/gi, "Universitas")
    .replace(/\s+/g, " ")
    .trim();
}

export function buildIndonesianPoiSearchPlan(query: string): PoiSearchPlan {
  const original = query.trim().replace(/\s+/g, " ");
  if (!original) return { primaryQuery: "" };

  // 1. Fuel station check (SPBU) -> raw query with Foursquare Fuel Stations category
  if (/\bSPBU\b/i.test(original)) {
    return {
      primaryQuery: original,
      foursquareCategoryIds: [FOURSQUARE_FUEL_STATION_CATEGORY_ID],
    };
  }

  // 2. Education check (SMAN, SMKN, SMPN, SDN, Univ) -> expanded is PRIMARY, raw is FALLBACK
  const educationExpanded = normalizeIndonesianEducationQuery(original);

  if (educationExpanded.toLowerCase() !== original.toLowerCase()) {
    return {
      primaryQuery: educationExpanded,
      fallbackQuery: original,
    };
  }

  // 3. Healthcare check (RSUD, RSUP, RS) -> raw is PRIMARY, expanded is FALLBACK
  const healthcareExpanded = original
    .replace(/\bRSUD\b/gi, "Rumah Sakit Umum Daerah")
    .replace(/\bRSUP\b/gi, "Rumah Sakit Umum Pusat")
    .replace(/\bRS\b/gi, "Rumah Sakit")
    .replace(/\s+/g, " ")
    .trim();

  if (healthcareExpanded.toLowerCase() !== original.toLowerCase()) {
    return {
      primaryQuery: original,
      fallbackQuery: healthcareExpanded,
    };
  }

  // 4. KUA check -> raw is PRIMARY, expanded is FALLBACK
  const kuaExpanded = original
    .replace(/\bKUA\b/gi, "Kantor Urusan Agama")
    .replace(/\s+/g, " ")
    .trim();

  if (kuaExpanded.toLowerCase() !== original.toLowerCase()) {
    return {
      primaryQuery: original,
      fallbackQuery: kuaExpanded,
    };
  }

  // 5. Default -> raw query as primary, no fallback
  return {
    primaryQuery: original,
  };
}

export function normalizeIndonesianPoiQuery(query: string): string {
  return buildIndonesianPoiSearchPlan(query).primaryQuery;
}

export function normalizeIndonesianAddressQuery(query: string): string {
  let cleaned = query.trim().replace(/\s+/g, " ");
  if (!cleaned) return "";

  // Conservative aliases:
  // Jl / Jln / Jl. / Jln. -> Jalan
  // Gg / Gg. -> Gang
  // Kp / Kp. -> Kampung
  // Ds / Ds. -> Desa
  // Kel / Kel. -> Kelurahan
  // Kec / Kec. -> Kecamatan
  // Kab / Kab. -> Kabupaten
  // Prov / Prov. -> Provinsi
  // Perum -> Perumahan
  // Kompl / Komp -> Kompleks
  // Kav / Kav. -> Kaveling

  cleaned = cleaned
    .replace(/\bJln?\b\.?/gi, "Jalan")
    .replace(/\bGg\b\.?/gi, "Gang")
    .replace(/\bKp\b\.?/gi, "Kampung")
    .replace(/\bDs\b\.?/gi, "Desa")
    .replace(/\bKel\b\.?/gi, "Kelurahan")
    .replace(/\bKec\b\.?/gi, "Kecamatan")
    .replace(/\bKab\b\.?/gi, "Kabupaten")
    .replace(/\bProv\b\.?/gi, "Provinsi")
    .replace(/\bPerum\b\.?/gi, "Perumahan")
    .replace(/\bKompl?\b\.?/gi, "Kompleks")
    .replace(/\bKav\b\.?/gi, "Kaveling");

  // Canonicalize No / No. / Nomor values:
  // e.g. "No 42", "No. 42", "Nomor 42" -> "Nomor 42"
  cleaned = cleaned.replace(/\b(?:no|nomor)\b\.?\s*(\d+)/gi, "Nomor $1");

  // Preserve RT / RW, Roman numerals, unit, blok, km, etc.
  return cleaned.replace(/\s+/g, " ").trim();
}
