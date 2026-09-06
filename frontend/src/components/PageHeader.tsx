/**
 * The frame every screen inside the shell shares, and the heading block at the top of it.
 *
 * **One measure for the whole application.** Each page used to choose between three
 * container widths, so moving from the catalogue to a scenario to the history moved the
 * left edge of the content from 1120 px to 768 px to 1024 px. Every navigation shifted the
 * page under the pointer, which reads as three products rather than one — and the reason
 * given for it, that a heatmap wants more room than a paragraph, is real but was solved at
 * the wrong level.
 *
 * It is solved here at the right one: the *frame* never moves, and running text narrows
 * itself with `Prose`. A paragraph gets its comfortable measure without the card above it
 * changing size, which is the actual requirement.
 *
 * **The measure is 72 rem, and it used to be 96.** The wider cap was chosen so a grid of
 * scenarios could use a large display, and what it did in practice was let a one-line
 * notice, a row of four figures and a list of five links stretch across the entire width
 * of a 1440 px screen with nothing in the right-hand two thirds of them. Content that is
 * wide because it has nowhere to stop does not look generous; it looks empty. At 72 rem a
 * three-column grid still has room and a notice is still a notice. The gutter *around*
 * the frame is the shell's, and it is the same on every section.
 */

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Page({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("mx-auto flex w-full max-w-6xl flex-col gap-8", className)}>
      {children}
    </div>
  );
}

/**
 * A column of running text, at the width the eye can track.
 *
 * Around 70 characters, which is where a reader stops losing the start of the next line.
 * It narrows its own contents and nothing else — the page around it keeps its size.
 */
export function Prose({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return <div className={cn("w-full max-w-[70ch]", className)}>{children}</div>;
}

/**
 * A page's title, what it is for, and anything that acts on the whole page.
 *
 * Every screen uses it, including the detail pages that used to write their own heading
 * with a slightly different size and no rule under it. The `eyebrow` is what those pages
 * needed and did not have: the level badge above a scenario's name, the date above a
 * sitting's.
 *
 * The block is separated from what follows by a rule, so the heading is read as the
 * heading and the first card is read as content rather than as more of the same grey.
 * `actions` sits on the same row from `sm` up and wraps beneath the text below it, rather
 * than being pushed off the edge — the narrow case is a phone, which is where a refresh
 * button being reachable matters most.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  /** Badges or a date above the title — what kind of thing this page is about. */
  eyebrow?: ReactNode;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4 border-b border-border pb-6">
      <div className="flex min-w-0 flex-col gap-2">
        {eyebrow && <div className="flex flex-wrap items-center gap-2">{eyebrow}</div>}
        <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          {title}
        </h1>
        {description && (
          <div className="max-w-[64ch] text-base text-muted-foreground">{description}</div>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}
