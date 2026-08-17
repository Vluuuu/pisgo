import { autocompleteLocation } from "@/lib/geoapify/autocomplete";

export async function GET(request: Request) {
  const query = new URL(request.url).searchParams.get("q")?.trim() ?? "";
  if (query.length < 3 || query.length > 160) {
    return Response.json({ error: "Enter at least 3 characters to search." }, { status: 400 });
  }

  try {
    return Response.json({ results: await autocompleteLocation(query) });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Location search failed.";
    return Response.json({ error: message }, { status: 502 });
  }
}
