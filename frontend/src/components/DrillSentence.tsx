/**
 * A drill's sentence: as it was said, or as it is to be said, with the corrections marked.
 *
 * The same pieces render both ways, so the two lines on the drill page cannot disagree
 * about where a correction is. As said, the corrected words are marked the way the
 * transcript and the grammar page mark them — amber and solid when the correction counts,
 * grey and dotted when it does not. As it is to be said, the corrections' words are what
 * the learner is about to say, so the one being practised is the one drawn strongest.
 */

import type { Drill } from "@/lib/api";
import { cn } from "@/lib/utils";

export function DrillSentence({
  drill,
  as,
  className,
}: {
  drill: Drill;
  as: "said" | "say";
  className?: string;
}) {
  const counted = new Map(drill.corrections.map((c) => [c.id, c.counted]));

  return (
    <p className={cn("leading-relaxed", className)} data-testid={`drill-${as}`}>
      {drill.cut_before && <span aria-hidden="true">…</span>}
      {drill.pieces.map((piece, index) => {
        const text = as === "said" ? piece.said : piece.say;
        if (piece.correction_id === null) return <span key={index}>{text}</span>;
        if (as === "said") {
          return (
            <mark
              key={index}
              className={cn(
                "rounded-sm px-0.5 text-inherit underline decoration-2 underline-offset-2",
                counted.get(piece.correction_id)
                  ? "bg-chart-2/20 decoration-chart-2"
                  : "bg-muted decoration-muted-foreground decoration-dotted",
              )}
            >
              {text}
            </mark>
          );
        }
        return (
          <strong
            key={index}
            className={cn(
              "underline decoration-2 underline-offset-4",
              piece.correction_id === drill.id
                ? "font-semibold decoration-primary"
                : "font-medium decoration-muted-foreground decoration-dotted",
            )}
          >
            {text}
          </strong>
        );
      })}
      {drill.cut_after && <span aria-hidden="true">…</span>}
    </p>
  );
}
