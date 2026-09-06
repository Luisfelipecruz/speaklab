"use client";

/**
 * The frame every signed-in screen sits in: a navigation rail, a thin top bar, and the
 * page.
 *
 * **It never blocks on the session check.** `status` is three-valued, and rendering
 * nothing while it is "checking" would blank the page on every navigation for somebody
 * who is already signed in. The navigation is there from the first paint; only the
 * identity slot in the rail's footer waits, and it waits by reserving space rather than
 * by spinning.
 *
 * **It imposes no maximum width.** The measure belongs to `Page`, which gives every
 * screen the same one — the shell's job is the padding around it, not the size of it.
 *
 * **The padding is one value, `GUTTER`, and it is the same on every section.** The space
 * between the rail and the content is what makes a page look placed rather than poured
 * in, and it only does that if it is constant: a gutter that is 32 px on one section and
 * 32 px on the next but with the content box a different width reads as movement. The
 * top bar shares it, so the navigation control, the title and the first card all start
 * on the same vertical line.
 *
 * The top bar exists for one control — the button that opens the rail on a phone, where
 * it is a sheet rather than a permanent column. It also carries the sign-out, which needs
 * a router and so cannot live in a server layout.
 *
 * `open` is read on the server from a cookie the sidebar writes, so a collapsed rail is
 * still collapsed after a reload without a frame of it being open first.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";
import { LogOutIcon } from "lucide-react";

import { AppSidebar, type ShellFacts } from "@/components/AppSidebar";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

/**
 * The horizontal space between the frame and whatever is inside it, on every signed-in
 * screen. Exported so a test can assert that the sections share it rather than each
 * choosing their own.
 */
export const GUTTER = "px-5 sm:px-8 lg:px-12 2xl:px-16";

export function AppShell({
  children,
  facts = null,
  defaultOpen = true,
}: {
  children: ReactNode;
  facts?: ShellFacts | null;
  defaultOpen?: boolean;
}) {
  const { user, status, signOut } = useAuth();
  const router = useRouter();

  return (
    <SidebarProvider defaultOpen={defaultOpen}>
      <AppSidebar facts={facts} />

      <SidebarInset>
        <header
          className={cn(
            "sticky top-0 z-10 flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background/90 backdrop-blur supports-[backdrop-filter]:bg-background/75",
            GUTTER,
          )}
        >
          <NavigationTrigger />
          <Separator orientation="vertical" className="mr-1 h-5" />
          <Link href="/home" className="text-sm font-medium tracking-tight md:hidden">
            SpeakLab
          </Link>

          <div className="ml-auto flex items-center gap-2">
            {/* In the top bar rather than the rail's footer. It stays reachable when the
                rail is collapsed to icons, and the bottom-left corner it would otherwise
                sit in is where Next's development overlay puts its own button — which
                covers it completely while anybody is working on this. */}
            <ThemeToggle />

            {status === "checking" ? (
              <span className="h-4 w-20" aria-hidden="true" />
            ) : user ? (
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
                <LogOutIcon />
                Sign out
              </Button>
            ) : (
              <Button asChild variant="outline" size="sm">
                <Link href="/login">Sign in</Link>
              </Button>
            )}
          </div>
        </header>

        {/* A div, not a `<main>`. `SidebarInset` is itself the main landmark, and a
            second one nested inside it leaves a screen reader offering two "main"
            regions to jump to, neither of which is wrong and only one of which is the
            page. */}
        <div className={cn("flex-1 py-8 lg:py-10", GUTTER)}>{children}</div>
      </SidebarInset>
    </SidebarProvider>
  );
}

/**
 * The control that opens the navigation, and the focus it has to give back.
 *
 * On a phone the rail is a dialog, and a dialog returns focus to whatever opened it —
 * except that the thing which opened this one is not the dialog's own trigger. It is this
 * button, sitting outside the dialog and flipping a flag in the sidebar's state, so
 * closing the sheet drops focus on `<body>` and a keyboard user is returned to the top of
 * the document to walk the page again. Putting it back is this component's whole job.
 *
 * Its own component rather than part of the shell because reading the sidebar's state
 * requires being inside the provider the shell renders.
 */
function NavigationTrigger() {
  const { isMobile, openMobile } = useSidebar();
  const trigger = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);

  useEffect(() => {
    if (isMobile && wasOpen.current && !openMobile) trigger.current?.focus();
    wasOpen.current = openMobile;
  }, [isMobile, openMobile]);

  // The vendored name for this control is "Toggle Sidebar", which names the furniture
  // rather than what it does.
  return <SidebarTrigger ref={trigger} aria-label="Toggle navigation" />;
}
