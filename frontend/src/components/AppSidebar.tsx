"use client";

/**
 * The navigation rail: where you are, where else you can go, and what is waiting there.
 *
 * **A rail rather than a row of links, because of the second column of information.** The
 * sections are peers a person moves between mid-task, and a horizontal bar has room
 * for their names and nothing else. A vertical one has room for the fact that decides
 * whether the section is worth opening — how many conversations are stored, how many
 * readings have been scored, whether the figures on the progress page are behind the
 * practice that produced them. Those counts arrive from the layout above, already
 * server-rendered, so the rail is complete at first paint rather than one round trip
 * after it.
 *
 * **The counts are absent, not zero, for a signed-out reader.** `facts` is null then, and
 * a badge reading "0 conversations" beside a sign-in prompt states something false about
 * an account nobody has identified yet.
 *
 * Below the medium breakpoint the same markup becomes a sheet, because practice happens
 * on the device the microphone is in and a permanent rail on a 375 px screen is most of
 * the screen.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ClipboardListIcon,
  DownloadIcon,
  HistoryIcon,
  HomeIcon,
  MessagesSquareIcon,
  MicIcon,
  PresentationIcon,
  SpellCheckIcon,
  TrendingUpIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
  useSidebar,
} from "@/components/ui/sidebar";
import { useAuth } from "@/hooks/useAuth";
import { PUBLIC_API_URL } from "@/lib/api";

/**
 * What the rail can say about each section without asking the API for anything new.
 *
 * Everything here is read off one snapshot response the layout already fetches. Adding a
 * count that needed its own request would put a network call on every page in the
 * product to decorate a menu.
 */
export interface ShellFacts {
  sessions: number;
  attempts: number;
  /** Weeks with practice in them — the closest thing to a streak that is actually counted. */
  periods: number;
  /** Something has been analysed or scored since the figures were last computed. */
  stale: boolean;
}

interface Section {
  href: string;
  label: string;
  icon: typeof HomeIcon;
  /** One line, shown in the collapsed rail's tooltip. */
  hint: string;
  badge?: (facts: ShellFacts) => string | null;
}

const SECTIONS: readonly Section[] = [
  {
    href: "/home",
    label: "Home",
    icon: HomeIcon,
    hint: "What to practise next",
  },
  {
    href: "/scenarios",
    label: "Scenarios",
    icon: MessagesSquareIcon,
    hint: "Role-play with a goal and a persona who pushes back",
  },
  {
    href: "/read",
    label: "Read aloud",
    icon: MicIcon,
    hint: "Passages scored sound by sound",
    badge: (facts) => (facts.attempts > 0 ? String(facts.attempts) : null),
  },
  {
    href: "/sessions",
    label: "History",
    icon: HistoryIcon,
    hint: "Every conversation you have practised",
    badge: (facts) => (facts.sessions > 0 ? String(facts.sessions) : null),
  },
  {
    href: "/grammar",
    label: "Grammar",
    icon: SpellCheckIcon,
    hint: "Your corrections, in your own sentences",
  },
  {
    href: "/answers",
    label: "Make your point",
    icon: PresentationIcon,
    hint: "Answer a work question out loud, and see how it was built",
  },
  {
    href: "/progress",
    label: "Progress",
    icon: TrendingUpIcon,
    hint: "Trends counted from what you recorded",
    badge: (facts) => (facts.stale ? "new" : null),
  },
];

/**
 * Whether a section owns the current address.
 *
 * A prefix test, so `/sessions/12` still marks History — but anchored at a segment
 * boundary. A plain `startsWith` would light up `/read` for a future `/reading-list`,
 * and the current section is the whole of the wayfinding here.
 */
export function isCurrent(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppSidebar({ facts }: { facts: ShellFacts | null }) {
  const pathname = usePathname();
  const { user, status } = useAuth();
  const { setOpenMobile, isMobile } = useSidebar();

  // On a phone the rail is a sheet over the page, and a link that leaves it open covers
  // the screen the person just navigated to.
  const dismiss = () => {
    if (isMobile) setOpenMobile(false);
  };

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <Link
          href="/home"
          onClick={dismiss}
          className="flex h-10 items-center gap-2.5 px-2 text-base font-semibold tracking-tight"
        >
          <span
            aria-hidden="true"
            className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground"
          >
            <ClipboardListIcon className="size-4" />
          </span>
          <span className="truncate group-data-[collapsible=icon]:hidden">SpeakLab</span>
        </Link>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Practise</SidebarGroupLabel>
          <SidebarGroupContent>
            {/* A real landmark. The vendored sidebar is divs all the way down, and
                without this there is nothing for "skip to navigation" to find. */}
            <nav aria-label="Sections">
              <SidebarMenu>
                {SECTIONS.map((section) => {
                  const current = isCurrent(pathname, section.href);
                  const badge = facts && section.badge ? section.badge(facts) : null;
                  return (
                    <SidebarMenuItem key={section.href}>
                      <SidebarMenuButton
                        asChild
                        isActive={current}
                        tooltip={section.hint}
                        // Taller than the vendored default, and the icon takes the
                        // accent when the section is current: the highlight is the
                        // answer to "where am I" for anyone who can see it, so it has
                        // to be visible at a glance rather than on inspection.
                        className="h-9 px-2.5 data-active:[&_svg]:text-primary"
                        // `aria-current` is what a screen reader uses to answer "where am
                        // I"; the highlight only answers it for someone who can see it.
                        aria-current={current ? "page" : undefined}
                      >
                        <Link href={section.href} onClick={dismiss}>
                          <section.icon />
                          <span>{section.label}</span>
                        </Link>
                      </SidebarMenuButton>
                      {badge && <SidebarMenuBadge>{badge}</SidebarMenuBadge>}
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </nav>
          </SidebarGroupContent>
        </SidebarGroup>

        {facts && facts.periods > 0 && (
          <SidebarGroup className="group-data-[collapsible=icon]:hidden">
            <SidebarGroupLabel>So far</SidebarGroupLabel>
            <SidebarGroupContent className="px-2 text-xs text-muted-foreground">
              <p>
                {facts.periods} week{facts.periods === 1 ? "" : "s"} with practice in
                {facts.periods === 1 ? " it" : " them"}, {facts.sessions} conversation
                {facts.sessions === 1 ? "" : "s"} and {facts.attempts} scored reading
                {facts.attempts === 1 ? "" : "s"}.
              </p>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>

      <SidebarFooter>
        <SidebarSeparator />
        <div className="flex h-7 items-center px-2 group-data-[collapsible=icon]:hidden">
          {status === "checking" ? (
            // Reserved space rather than a spinner. The rail is not what the person came
            // for, and a spinner in it draws the eye to the least useful part of the page.
            <span className="h-4 flex-1" aria-hidden="true" />
          ) : user ? (
            <span
              className="min-w-0 flex-1 truncate text-xs text-muted-foreground"
              title={user.email}
            >
              {user.email}
            </span>
          ) : null}
        </div>

        {user && (
          // A plain link to the API rather than a fetch. The API answers with an
          // attachment, so the browser saves the file itself, and a top-level navigation
          // carries the session cookie with it.
          <a
            href={`${PUBLIC_API_URL}/progress/export`}
            className="flex items-center gap-2 px-2 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline group-data-[collapsible=icon]:hidden"
          >
            <DownloadIcon className="size-3.5 shrink-0" aria-hidden="true" />
            Download your history
          </a>
        )}

        {facts?.stale && (
          <Badge
            variant="secondary"
            className="mx-1 justify-start group-data-[collapsible=icon]:hidden"
          >
            Progress figures are behind
          </Badge>
        )}
      </SidebarFooter>
    </Sidebar>
  );
}
