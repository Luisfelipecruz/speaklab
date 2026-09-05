/**
 * The two things every screen inside the shell declares for itself: how wide it wants to
 * be, and what it is called.
 *
 * **Width is a property of the page, not of the frame.** The shell used to cap everything
 * at 1024 px, which is a reasonable measure for a paragraph and an absurd one for a
 * heatmap of forty sounds across twelve weeks — on a wide display it left most of the
 * screen as margin and squeezed the one thing that needed the room. So the frame imposes
 * nothing and each page says which of three answers applies to it. Three, not a free
 * value: an open `max-w-*` on every page is how a product ends up with eleven slightly
 * different content widths.
 *
 * - `prose` — text meant to be read in sequence. Around 65 characters, which is where
 *   the eye stops losing the start of the next line.
 * - `wide` — lists, forms and transcripts: wider than prose, still bounded, because a
 *   two-word row stretched across 2560 px is unreadable in the other direction.
 * - `full` — charts and grids, which are the only things that genuinely improve with
 *   more room.
 */

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type PageWidth = "prose" | "wide" | "full";

const WIDTH: Record<PageWidth, string> = {
  prose: "max-w-3xl",
  wide: "max-w-5xl",
  full: "max-w-[110rem]",
};

export function Page({
  width,
  className,
  children,
}: {
  width: PageWidth;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("mx-auto flex w-full flex-col gap-8", WIDTH[width], className)}>
      {children}
    </div>
  );
}

/**
 * A page's title, what it is for, and anything that acts on the whole page.
 *
 * `actions` sits on the same row from `sm` up and wraps beneath the text below it, rather
 * than being pushed off the edge — the narrow case is a phone, which is where a refresh
 * button being reachable matters most.
 */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
        {description && (
          <div className="max-w-2xl text-sm text-muted-foreground sm:text-base">
            {description}
          </div>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}
