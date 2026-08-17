export function getGeoapifyApiKey(): string {
  const apiKey = process.env.GEOAPIFY_API_KEY;
  if (!apiKey) throw new Error("Geoapify is not configured. Add GEOAPIFY_API_KEY to apps/web/.env.local.");
  return apiKey;
}
