const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function parseIsoDate(value: string): Date {
  if (!ISO_DATE.test(value)) throw new Error("Date must use YYYY-MM-DD format.");
  const date = new Date(`${value}T00:00:00.000Z`);
  if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value) {
    throw new Error("Date is invalid.");
  }
  return date;
}

export function dateToIso(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function todayIso(): string {
  return dateToIso(new Date());
}

export function daysBetween(start: string, end: string): number {
  return Math.floor((parseIsoDate(end).getTime() - parseIsoDate(start).getTime()) / 86_400_000);
}

export function addCalendarDays(value: string, days: number): string {
  const date = parseIsoDate(value);
  date.setUTCDate(date.getUTCDate() + days);
  return dateToIso(date);
}
