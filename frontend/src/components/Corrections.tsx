/**
 * A turn's transcript with its corrections marked where they happened, and the list
 * that explains each mark.
 *
 * **The mark carries a number and the number carries the meaning.** A highlighted
 * stretch says only "this was flagged"; the numbered row under the bubble says what was
 * proposed instead, which category it was filed under, and whether it counts. A tooltip
 * would put the explanation where a phone cannot reach it and a screen reader would not
 * announce it; a row is reachable by everyone.
 *
 * **Two kinds of mark, on purpose.** A correction sitting on words the recogniser was
 * unsure of, or one the model itself hedged on, is drawn dotted and grey and its row says
 * so — it is shown because a transcript with a hole in it is worse than one with a
 * doubtful correction on it, and it is kept out of every rate for the same reason the
 * report keeps it out. The badge is the whole difference and the learner can see it.
 *
 * **A rule's correction is marked like a model's, and its row says where it came from.**
 * The mark answers "where"; a second colour of solid underline would read as a second
 * severity, which it is not. The row answers "what and why", so that is where the
 * source goes.
 */

import { SpellCheck } from "lucide-react";

import { humanise } from "@/components/ScenarioCard";
import { Badge } from "@/components/ui/badge";
import type { MarkedTranscript, NumberedCorrection } from "@/lib/corrections";
import { cn } from "@/lib/utils";

function Number_({ n, counted }: { n: number; counted: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex size-4 shrink-0 items-center justify-center rounded-full text-[0.65rem] font-semibold tabular-nums",
        counted ? "bg-chart-2/20 text-foreground" : "bg-muted text-muted-foreground",
      )}
    >
      {n}
    </span>
  );
}

/** Says a correction was found by a grammar rule rather than proposed by the model. */
export function RuleBadge() {
  return (
    <Badge variant="outline" className="text-xs">
      grammar rule
    </Badge>
  );
}

export function MarkedText({ marked }: { marked: MarkedTranscript }) {
  return (
    <p className="text-sm leading-relaxed whitespace-pre-wrap">
      {marked.segments.map((segment, index) =>
        segment.correction ? (
          <mark
            key={index}
            className={cn(
              "rounded-sm px-0.5 text-inherit underline decoration-2 underline-offset-2",
              segment.correction.item.counted
                ? "bg-chart-2/20 decoration-chart-2"
                : "bg-muted decoration-muted-foreground decoration-dotted",
            )}
          >
            {segment.text}
            <sup className="ml-0.5 text-[0.7em] font-semibold">
              {segment.correction.number}
            </sup>
            <span className="sr-only">, correction {segment.correction.number},</span>
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </p>
  );
}

function Row({ correction }: { correction: NumberedCorrection }) {
  const { item, number } = correction;
  return (
    <li className="flex gap-2">
      <Number_ n={number} counted={item.counted} />
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
          <span className="text-muted-foreground line-through">{item.original}</span>
          <span aria-hidden="true">→</span>
          <span className="font-medium">{item.correction}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline" className="text-xs">
            {humanise(item.category.toLowerCase())}
            {item.subcategory ? ` · ${humanise(item.subcategory)}` : ""}
          </Badge>
          {item.detector === "rule" && <RuleBadge />}
          {!item.counted && (
            <Badge variant="secondary" className="text-xs">
              {item.asr_suspect ? "may be a mishearing" : "low confidence"}
            </Badge>
          )}
          {!correction.placed && (
            <span className="italic">not marked above — the words could not be placed</span>
          )}
          {item.explanation && <span>{item.explanation}</span>}
        </div>
      </div>
    </li>
  );
}

export function CorrectionList({ corrections }: { corrections: NumberedCorrection[] }) {
  if (corrections.length === 0) return null;
  return (
    <div className="flex flex-col gap-2 border-t border-border pt-3">
      <h4 className="flex items-center gap-1.5 text-xs font-medium tracking-wider text-muted-foreground uppercase">
        <SpellCheck className="size-3.5 text-primary" aria-hidden="true" />
        Proposed corrections
      </h4>
      <ol aria-label="Proposed corrections" className="flex flex-col gap-2">
        {corrections.map((correction) => (
          <Row key={correction.number} correction={correction} />
        ))}
      </ol>
    </div>
  );
}
