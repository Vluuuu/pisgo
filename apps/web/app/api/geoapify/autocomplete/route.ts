import { NextResponse } from "next/server";

// Deprecated compatibility endpoint. Use /api/locations for hybrid TomTom/Foursquare location search.
export async function GET() {
  return NextResponse.json(
    { error: "This endpoint is deprecated. Use /api/locations." },
    { status: 410 },
  );
}
