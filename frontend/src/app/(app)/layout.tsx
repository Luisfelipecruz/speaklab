/**
 * One frame for the five signed-in sections.
 *
 * **`(app)` is a route group: the parentheses keep it out of the URL.** Nothing moves —
 * `/scenarios`, `/read`, `/sessions` and `/progress` are still at those addresses — and
 * the four near-identical layouts that each wrapped one section are now this file.
 *
 * It is a server component, which is what lets the rail's counts be correct at first
 * paint. It reads two things the browser cannot supply on its own: the practice snapshot,
 * fetched with the session cookie forwarded, and whether the rail was left collapsed,
 * which the sidebar stores in a cookie precisely so the server can answer it before the
 * first frame instead of after it.
 *
 * **A failure here degrades the rail, it does not take the page down.** The counts are a
 * decoration on a menu; the page inside reports its own trouble in its own words, and a
 * shell that threw would replace that with a generic error boundary saying less.
 */

import { cookies } from "next/headers";

import { AppShell } from "@/components/AppShell";
import type { ShellFacts } from "@/components/AppSidebar";
import type { Progress } from "@/lib/api";
import { serverRequestOrNull } from "@/lib/server-api";

export const dynamic = "force-dynamic";

/** What the sidebar writes when it is collapsed or expanded. */
const SIDEBAR_COOKIE = "sidebar_state";

async function loadFacts(): Promise<ShellFacts | null> {
  let progress: Progress | null = null;
  try {
    progress = await serverRequestOrNull<Progress>("/progress");
  } catch {
    return null;
  }
  if (!progress) return null;

  return {
    sessions: progress.totals.sessions,
    attempts: progress.totals.attempts,
    periods: progress.totals.periods,
    stale: progress.stale,
  };
}

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const [facts, jar] = await Promise.all([loadFacts(), cookies()]);
  const stored = jar.get(SIDEBAR_COOKIE)?.value;

  return (
    <AppShell facts={facts} defaultOpen={stored !== "false"}>
      {children}
    </AppShell>
  );
}
