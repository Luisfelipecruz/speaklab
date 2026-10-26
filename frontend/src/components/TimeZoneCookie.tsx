"use client";

/**
 * Names the browser's time zone to the server, once, so a server-rendered time is the
 * reader's. When the cookie was missing or out of date the page is rendered again with it.
 */

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ZONE_COOKIE } from "@/lib/time";

export function TimeZoneCookie() {
  const router = useRouter();

  useEffect(() => {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (!zone) return;
    const current = document.cookie
      .split("; ")
      .find((entry) => entry.startsWith(`${ZONE_COOKIE}=`))
      ?.slice(ZONE_COOKIE.length + 1);
    if (current === encodeURIComponent(zone)) return;
    document.cookie = `${ZONE_COOKIE}=${encodeURIComponent(zone)}; path=/; max-age=31536000; samesite=lax`;
    router.refresh();
  }, [router]);

  return null;
}
