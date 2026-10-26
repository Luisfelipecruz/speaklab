/**
 * What a check found in the person's English: their text with each fix marked where it
 * is, and a numbered list saying what it should be, why, and what found it.
 *
 * The marks come from the same marker the transcripts use, so a fix whose span does not
 * hold its words is listed and not underlined. Whether a fix counts is said on its row:
 * English the person typed counts as writing; English they said is shown and not counted,
 * because speech is measured in conversations; and nothing counts while saving is paused.
 */

import { Badge } from "@/components/ui/badge";
import { MarkedText } from "@/components/Corrections";
import type { CaptureFix } from "@/lib/api";
import { markTranscript } from "@/lib/corrections";
import { asMarked, sourceOf } from "@/lib/notebook";
import { cn } from "@/lib/utils";

export function CaptureFixes({
  text,
  fixes,
  uncounted,
}: {
  text: string;
  fixes: CaptureFix[];
  /** Why none of these counts, when none does: said aloud, or saving paused. */
  uncounted?: string;
}) {
  if (fixes.length === 0) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-base leading-relaxed">{text}</p>
        <p className="text-sm text-muted-foreground" data-testid="no-fixes">
          Nothing to fix: the dictionary, the grammar rules and the model found no mistake.
        </p>
      </div>
    );
  }
  // The marker hands back the items it was given, so each row finds its own fix again.
  const items = fixes.map(asMarked);
  const fixOf = new Map(items.map((item, index) => [item, fixes[index]!]));
  const marked = markTranscript(text, items);
  return (
    <div className="flex flex-col gap-3">
      <MarkedText marked={marked} />
      <ol aria-label="Fixes" className="flex flex-col gap-2">
        {marked.corrections.map(({ item, number }) => {
          const fix = fixOf.get(item)!;
          return (
            <li key={number} className="flex gap-2 text-sm">
              <span
                className={cn(
                  "inline-flex size-5 shrink-0 items-center justify-center rounded-full text-xs font-semibold tabular-nums",
                  item.counted ? "bg-chart-2/20" : "bg-muted text-muted-foreground",
                )}
              >
                {number}
              </span>
              <div className="flex min-w-0 flex-col gap-1">
                <div className="flex flex-wrap items-center gap-x-2">
                  <span className="text-muted-foreground line-through">{item.original}</span>
                  <span aria-hidden="true">→</span>
                  <span className="font-medium">{item.correction}</span>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="outline" className="text-xs">
                    {fix.label}
                  </Badge>
                  <span>{sourceOf(fix)}</span>
                  {uncounted ? (
                    <Badge variant="secondary" className="text-xs">
                      {uncounted}
                    </Badge>
                  ) : (
                    !item.counted && (
                      <Badge variant="secondary" className="text-xs">
                        low confidence, not counted
                      </Badge>
                    )
                  )}
                  {item.explanation && <span>{item.explanation}</span>}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
