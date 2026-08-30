/**
 * The catalogue and everything under it, inside the application frame.
 *
 * Two of these exist — one here and one under `sessions/` — rather than a single
 * `(app)` route group. The route group would be tidier by one file, and it would move
 * every page in this milestone to a path the implementation plan does not name. Two
 * four-line layouts is the cheaper of the two kinds of drift.
 */

import { AppShell } from "@/components/AppShell";

export default function ScenariosLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
