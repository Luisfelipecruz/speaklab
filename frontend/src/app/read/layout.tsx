/**
 * Read-aloud, inside the application frame. A per-section layout rather than a route
 * group: there are too few of these for the extra indirection to pay.
 */

import { AppShell } from "@/components/AppShell";

export default function ReadLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
