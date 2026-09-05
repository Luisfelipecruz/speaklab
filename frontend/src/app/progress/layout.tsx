/**
 * The progress page, inside the application frame.
 *
 * A third four-line layout beside the ones under `sessions/` and `scenarios/`, for the
 * reason given there: a shared route group would be tidier by two files and would move
 * every page to a path the plan does not name.
 */

import { AppShell } from "@/components/AppShell";

export default function ProgressLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
