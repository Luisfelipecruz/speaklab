"use client";

/**
 * The frame every signed-in screen sits in.
 *
 * It exists because a person who cannot get from a conversation back to the catalogue
 * has to type a URL. It is also the consumer of the session that renders *around* other
 * consumers, which is why `useAuth` is a provider rather than a plain hook.
 *
 * **It never blocks on the session check.** `status` is three-valued, and rendering
 * nothing while it is "checking" would blank the page on every navigation for somebody
 * who is already signed in. The header renders; only the identity slot waits.
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/scenarios", label: "Scenarios" },
  { href: "/read", label: "Read aloud" },
  { href: "/sessions", label: "History" },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const { user, status, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border">
        <div className="mx-auto flex w-full max-w-5xl items-center gap-6 px-6 py-3">
          <Link href="/" className="text-sm font-semibold tracking-tight">
            SpeakLab
          </Link>

          <nav aria-label="Main" className="flex items-center gap-4">
            {NAV.map((entry) => (
              <Link
                key={entry.href}
                href={entry.href}
                aria-current={pathname.startsWith(entry.href) ? "page" : undefined}
                className={cn(
                  "text-sm transition-colors hover:text-foreground",
                  pathname.startsWith(entry.href)
                    ? "font-medium text-foreground"
                    : "text-muted-foreground",
                )}
              >
                {entry.label}
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            {status === "checking" ? (
              // Reserved space rather than a spinner. The header is not what the person
              // came for, and a spinner in it draws the eye to the least useful part of
              // the page.
              <span className="h-4 w-24" aria-hidden="true" />
            ) : user ? (
              <>
                <span className="hidden text-xs text-muted-foreground sm:inline">
                  {user.email}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={async () => {
                    await signOut();
                    router.push("/login");
                    // The pages under this shell are server-rendered with the cookie
                    // forwarded, so without a refresh the previous account's history
                    // stays on screen after signing out.
                    router.refresh();
                  }}
                >
                  Sign out
                </Button>
              </>
            ) : (
              <Button asChild variant="outline" size="sm">
                <Link href="/login">Sign in</Link>
              </Button>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">{children}</main>
    </div>
  );
}
