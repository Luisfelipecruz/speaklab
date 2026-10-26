/**
 * Times as the person's clock reads them, on a page rendered by a server that is not on
 * their clock.
 *
 * A capture is a moment — "09:12, in Mail" — and the server rendering the Notebook runs in
 * a container on UTC. So the browser names its time zone once, in a cookie, and the
 * server formats with it. Before the cookie exists the server's own zone is used, which
 * in the desktop app is already the Mac's.
 */

export const ZONE_COOKIE = "speaklab_tz";

/** The zone, if the runtime knows it; otherwise undefined, which formats in its own. */
export function knownZone(zone: string | undefined | null): string | undefined {
  if (!zone) return undefined;
  try {
    new Intl.DateTimeFormat("en-GB", { timeZone: zone });
    return zone;
  } catch {
    return undefined;
  }
}

/** "09:12", on the 24-hour clock. */
export function timeOf(iso: string, zone?: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: knownZone(zone),
  }).format(new Date(iso));
}

/** "Tuesday 25 October". */
export function dayOf(iso: string, zone?: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: knownZone(zone),
  }).format(new Date(iso));
}

/** "2026-10-25": the calendar day, for grouping. */
export function dayKey(iso: string, zone?: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: knownZone(zone),
  }).formatToParts(new Date(iso));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/** Whole days from `from` to `iso`, by the calendar in `zone`. */
export function daysUntil(iso: string, zone?: string, from: Date = new Date()): number {
  const day = (key: string) => Date.parse(`${key}T00:00:00Z`);
  return Math.round((day(dayKey(iso, zone)) - day(dayKey(from.toISOString(), zone))) / 86_400_000);
}
