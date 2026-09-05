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
 * The cap is generous rather than absent. Wide displays are the case that motivated the
 * old `full`, and a grid of scenarios or a row of forty sounds does genuinely improve with
 * the room; a page with no maximum at all just makes a different mistake at 2560 px.
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
    <div className={cn("mx-auto flex w-full max-w-[96rem] flex-col gap-8", className)}>
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
          <div className="max-w-[70ch] text-sm text-muted-foreground sm:text-base">
            {description}
          </div>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}
