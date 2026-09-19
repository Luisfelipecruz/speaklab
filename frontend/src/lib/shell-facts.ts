/**
 * The counts the navigation rail shows, read off the one progress response the layout
 * fetches for every signed-in page.
 *
 * The History badge is the account's conversation count, not the window's session count.
 * The progress totals carry both: `sessions` is what the trend window rests on — sessions
 * with turns in them, summed period by period, so a conversation older than the window
 * drops out and one spanning two weeks is counted twice — and `conversations` is every
 * conversation on the account, counted the way the History page counts its list. A badge
 * on the link to that page has to agree with the page.
 *
 * A failure here degrades the rail, it does not take the page down: the counts are a
 * decoration on a menu, and the page inside reports its own trouble in its own words.
 */

import type { ShellFacts } from "@/components/AppSidebar";
import type { Progress } from "@/lib/api";
import { serverRequestOrNull } from "@/lib/server-api";

export async function loadShellFacts(): Promise<ShellFacts | null> {
  let progress: Progress | null = null;
  try {
    progress = await serverRequestOrNull<Progress>("/progress");
  } catch {
    return null;
  }
  if (!progress) return null;

  return {
    conversations: progress.totals.conversations,
    attempts: progress.totals.attempts,
    periods: progress.totals.periods,
    stale: progress.stale,
  };
}
