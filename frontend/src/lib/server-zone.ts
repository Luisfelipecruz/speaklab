/**
 * The reader's time zone, on the server: the one their browser named in a cookie.
 * Server components only, like `server-api.ts`.
 */

import { cookies } from "next/headers";

import { knownZone, ZONE_COOKIE } from "@/lib/time";

export async function readerZone(): Promise<string | undefined> {
  const raw = (await cookies()).get(ZONE_COOKIE)?.value;
  try {
    return knownZone(raw ? decodeURIComponent(raw) : undefined);
  } catch {
    return undefined;
  }
}
