export function getTomTomApiKey(): string {
  const apiKey = process.env.TOMTOM_API_KEY;
  if (!apiKey) throw new Error("TomTom is not configured. Add TOMTOM_API_KEY to apps/web/.env.local.");
  return apiKey;
}
