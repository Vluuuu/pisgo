export function formatDistance(meters: number): string {
  return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(meters / 1_000)} km`;
}

export function formatDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours ? `${hours} hr ${minutes ? `${minutes} min` : ""}`.trim() : `${minutes} min`;
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00.000Z`));
}
