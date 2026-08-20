import {
  fetchTomTomDetailsByMore,
  fetchTomTomSuggest,
} from "@/lib/tomtom/client";
import { normalizeIndonesianEducationQuery } from "@/lib/locations/normalizers";
import { searchLocationUnified } from "@/lib/locations/search";
import type { LocationFlowLinkage } from "@/types/location";

const UUID_V4_V7_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function sanitizeSessionId(sessionId: string | null): string | undefined {
  if (!sessionId) return undefined;
  const trimmed = sessionId.trim();
  if (UUID_V4_V7_RE.test(trimmed)) return trimmed;
  return undefined;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("q")?.trim() ?? "";
  const mode = searchParams.get("mode")?.trim() || "suggest";
  const sessionId = sanitizeSessionId(searchParams.get("sessionId"));

  if (!["suggest", "search"].includes(mode)) {
    return Response.json({ error: "Invalid search mode." }, { status: 400 });
  }

  if (query.length < 3 || query.length > 200) {
    return Response.json({ error: "Enter at least 3 characters to search." }, { status: 400 });
  }

  try {
    if (mode === "search") {
      const results = await searchLocationUnified(query, sessionId);
      return Response.json({ results });
    }

    const suggestQuery = normalizeIndonesianEducationQuery(query);
    const suggestions = await fetchTomTomSuggest(suggestQuery, sessionId, 6);
    return Response.json({ results: suggestions });
  } catch (error) {
    console.error("[locations] Search failed:", error);
    return Response.json({ error: "Location search is temporarily unavailable." }, { status: 502 });
  }
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as {
      more?: LocationFlowLinkage;
      sessionId?: string;
    };

    const sessionId = sanitizeSessionId(body.sessionId ?? null);

    if (!body.more || body.more.operation !== "details" || !Array.isArray(body.more.pathParameters)) {
      return Response.json({ error: "Invalid lookup parameters." }, { status: 400 });
    }

    const detail = await fetchTomTomDetailsByMore(body.more, sessionId);
    if (!detail) {
      return Response.json({ error: "Location details not found." }, { status: 404 });
    }

    return Response.json({ result: detail });
  } catch (error) {
    console.error("[locations] Details lookup failed:", error);
    return Response.json({ error: "Location details lookup is temporarily unavailable." }, { status: 502 });
  }
}
