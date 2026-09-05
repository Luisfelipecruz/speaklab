/**
 * Read-aloud, inside the application frame. The third of these, and the last: m10's
 * progress pages will make a route group worth the churn, not before.
 */

import { AppShell } from "@/components/AppShell";

export default function ReadLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
