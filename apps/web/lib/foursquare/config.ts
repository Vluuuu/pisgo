export function getFoursquareApiKey(): string {
  const apiKey = process.env.FOURSQUARE_API_KEY;
  if (!apiKey) throw new Error("Foursquare is not configured. Add FOURSQUARE_API_KEY to apps/web/.env.local.");
  return apiKey;
}
