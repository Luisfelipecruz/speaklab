/**
 * What to rehearse next, and what was counted to decide it.
 *
 * Every item prints its own measurement beside it — how many words, how many takes, how
 * many instances of a sound. That is the difference between a count and advice: a reader
 * who disagrees can see what the number was and go and look at the take it came from.
 *
 * Nothing here comes from a language model, and none of it moves the progress page.
 */

import Link from "next/link";
import { GaugeIcon, MessageSquareOffIcon, SpellCheckIcon, TextSearchIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import type { NextUp } from "@/lib/api";

const ICON = {
  fidelity: TextSearchIcon,
  sound: SpellCheckIcon,
  pace: GaugeIcon,
  filler: MessageSquareOffIcon,
} as const;

const LEAD = {
  fidelity: "Furthest from the script",
  sound: "The weakest sound",
  pace: "Over its target",
  filler: "Said most often",
} as const;

export function RehearseNext({
  items,
  presentationId,
  sectionIndexById,
  caveat,
}: {
  items: NextUp[];
  presentationId: number;
  /** Section ids to their position, so an item can link to the section it is about. */
  sectionIndexById: Map<number, number>;
  caveat: string;
}) {
  if (items.length === 0) return null;

  return (
    <section className="flex flex-col gap-3" aria-labelledby="next-up">
      <h2 id="next-up" className="text-lg font-semibold tracking-tight">
        What to rehearse next
      </h2>
      <ul className="grid gap-3 md:grid-cols-2">
        {items.map((item) => {
          const Icon = ICON[item.kind];
          const idx = item.section_id === null ? null : sectionIndexById.get(item.section_id);
          const body = (
            <CardContent className="flex items-start gap-3 py-4">
              <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="flex flex-col gap-1">
                <span className="text-xs uppercase tracking-wide text-muted-foreground">
                  {LEAD[item.kind]}
                </span>
                <span className="font-medium">{item.title}</span>
                <span className="text-sm text-muted-foreground">{item.reason}</span>
              </span>
            </CardContent>
          );
          return (
            <li key={`${item.kind}-${item.title}`}>
              {idx === undefined || idx === null ? (
                <Card>{body}</Card>
              ) : (
                <Link href={`/rehearse/${presentationId}/${idx}`} className="group block h-full">
                  <Card className="h-full transition-colors group-hover:border-primary">{body}</Card>
                </Link>
              )}
            </li>
          );
        })}
      </ul>
      <p className="text-sm text-muted-foreground">{caveat}</p>
    </section>
  );
}
