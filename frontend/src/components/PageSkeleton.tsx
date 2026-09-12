/**
 * What a section looks like while its server render is on the way.
 *
 * Every signed-in page is rendered on the server with the session cookie forwarded, so a
 * click on the rail waits for the API before anything changes. Without a loading boundary
 * the previous page stays on screen through that wait, and a person reads it as a click
 * that did nothing. The shell stays where it is; only the page area is replaced, by blocks
 * shaped like what is coming — a grid of cards, a list, a row of figures, one document —
 * so the layout does not jump when the real page lands.
 *
 * It says it is loading in words as well as in grey, because a pulsing block is nothing a
 * screen reader can announce.
 */

import type { ReactNode } from "react";

import { Page } from "@/components/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";

export type SkeletonShape = "cards" | "list" | "tiles" | "document";

const BODIES: Record<SkeletonShape, ReactNode> = {
  cards: (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }, (_, i) => (
        <Skeleton key={i} className="h-40 rounded-xl" />
      ))}
    </div>
  ),
  list: (
    <div className="flex flex-col divide-y divide-border rounded-xl border">
      {Array.from({ length: 5 }, (_, i) => (
        <div key={i} className="flex flex-col gap-2 px-5 py-4">
          <Skeleton className="h-4 w-2/3 max-w-md" />
          <Skeleton className="h-3 w-40" />
        </div>
      ))}
    </div>
  ),
  tiles: (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-48 rounded-xl" />
        <Skeleton className="h-48 rounded-xl" />
      </div>
    </div>
  ),
  document: (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-64 rounded-xl" />
      <Skeleton className="h-4 w-full max-w-2xl" />
      <Skeleton className="h-4 w-3/4 max-w-xl" />
      <Skeleton className="h-40 rounded-xl" />
    </div>
  ),
};

export function PageSkeleton({ shape, label }: { shape: SkeletonShape; label: string }) {
  return (
    <Page>
      <div role="status" data-shape={shape} className="flex flex-col gap-8">
        <span className="sr-only">{label}</span>
        <div aria-hidden="true" className="flex flex-col gap-3 border-b pb-6">
          <Skeleton className="h-8 w-64 max-w-full" />
          <Skeleton className="h-4 w-[32rem] max-w-full" />
        </div>
        <div aria-hidden="true">{BODIES[shape]}</div>
      </div>
    </Page>
  );
}
