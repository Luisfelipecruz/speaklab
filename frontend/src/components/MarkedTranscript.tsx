/**
 * The answer as the recogniser wrote it, with each counted signpost marked on its words.
 *
 * Every kind has its own underline colour and its own name in the legend, and the name is
 * also inside the mark for a screen reader — a colour alone says nothing to somebody who
 * cannot see it. The marks are neutral: a signpost is what the answer contains, not a
 * point scored, so none of them is green and none is red.
 */

import type { Counted } from "@/lib/api";
import { KIND_LABEL, segments } from "@/lib/answers";
import { cn } from "@/lib/utils";

const STYLE: Record<Counted["kind"], string> = {
  reason: "decoration-chart-1 bg-chart-1/10",
  example: "decoration-chart-2 bg-chart-2/10",
  sequence: "decoration-chart-3 bg-chart-3/10",
  contrast: "decoration-chart-4 bg-chart-4/10",
  close: "decoration-chart-5 bg-chart-5/10",
  repeat: "decoration-muted-foreground decoration-dashed",
};

export function MarkedTranscript({
  transcript,
  found,
}: {
  transcript: string;
  found: Counted[];
}) {
  const kinds = Array.from(new Set(found.map((item) => item.kind)));
  return (
    <div className="flex flex-col gap-3">
      <p className="text-base leading-8" data-testid="marked-transcript">
        {segments(transcript, found).map((piece, index) =>
          piece.kind ? (
            <mark
              key={index}
              className={cn(
                "rounded-sm px-0.5 text-foreground underline decoration-2 underline-offset-4",
                STYLE[piece.kind],
              )}
              title={KIND_LABEL[piece.kind]}
            >
              <span className="sr-only">{KIND_LABEL[piece.kind]}: </span>
              {piece.text}
            </mark>
          ) : (
            <span key={index}>{piece.text}</span>
          ),
        )}
      </p>
      {kinds.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Key">
          {kinds.map((kind) => (
            <li key={kind} className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className={cn("inline-block h-0.5 w-4 underline decoration-2", STYLE[kind])}
                style={{ borderBottom: "2px solid currentColor" }}
              />
              {KIND_LABEL[kind]}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
