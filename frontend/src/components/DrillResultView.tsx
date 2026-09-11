/**
 * What the recogniser heard when the sentence was said again.
 *
 * **What was heard, not a mark.** Each correction gets what stood where its words belong —
 * the corrected words, the words as first said, something else, or nothing — and the
 * sentence gets its words side by side with what was heard. There is no score and no pass:
 * the recogniser can hear a correct form where a wrong one was spoken, and the correction
 * itself may be wrong, so the page shows the evidence and leaves the verdict to the reader.
 * The four outcomes are drawn in the same neutral colours for the same reason — a red
 * cross beside a correction that was never right would be the product grading the learner
 * on its own mistake.
 */

import { Check, CircleDashed, MicOff, Undo2 } from "lucide-react";

import type { Drill, DrillResult, DrillVerdict, DrillVerdictKind } from "@/lib/api";

const OUTCOME: Record<DrillVerdictKind, { icon: typeof Check; text: string }> = {
  corrected: { icon: Check, text: "Heard as corrected" },
  original: { icon: Undo2, text: "Heard the way you first said it" },
  other: { icon: CircleDashed, text: "Heard something else there" },
  unheard: { icon: MicOff, text: "Nothing was heard where it belongs" },
};

function quoted(words: string): string {
  return words ? `“${words}”` : "nothing";
}

function Verdict({ verdict, drill }: { verdict: DrillVerdict; drill: Drill }) {
  const correction = drill.corrections.find((c) => c.id === verdict.id);
  const { icon: Icon, text } = OUTCOME[verdict.verdict];
  return (
    <li className="flex gap-3" data-testid={`verdict-${verdict.id}`}>
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div className="flex flex-col gap-0.5 text-sm">
        {correction && drill.corrections.length > 1 && (
          <span className="text-xs text-muted-foreground">
            {correction.original} → {correction.correction || "(removed)"}
          </span>
        )}
        <span>
          <span className="font-medium">{text}</span>
          {verdict.verdict !== "unheard" && <>: {quoted(verdict.heard)}</>}
          {verdict.verdict !== "corrected" && (
            <span className="text-muted-foreground"> — the correction is {quoted(verdict.expected)}</span>
          )}
          .
        </span>
        {verdict.unsure && (
          <span className="text-xs text-muted-foreground">
            The recogniser was unsure of these words, so this may be a mishearing.
          </span>
        )}
      </div>
    </li>
  );
}

function Comparison({ words }: { words: DrillResult["words"] }) {
  return (
    <p className="flex flex-wrap gap-x-1.5 gap-y-1 text-sm" aria-label="Word by word">
      {words.map((word, index) => {
        if (word.expected !== null && word.expected === word.heard) {
          return <span key={index}>{word.heard}</span>;
        }
        if (word.heard === null) {
          return (
            <span key={index} className="text-muted-foreground line-through">
              <span className="sr-only">not heard: </span>
              {word.expected}
            </span>
          );
        }
        if (word.expected === null) {
          return (
            <span key={index} className="italic text-muted-foreground">
              <span className="sr-only">heard, not in the sentence: </span>+{word.heard}
            </span>
          );
        }
        return (
          <span key={index} className="rounded-sm bg-muted px-1">
            <span className="sr-only">expected </span>
            <span className="text-muted-foreground line-through">{word.expected}</span>{" "}
            <span className="sr-only">, heard </span>
            {word.heard}
          </span>
        );
      })}
    </p>
  );
}

/** "12 of 13 words heard as written, 1 heard as something else." */
export function wordCounts(result: DrillResult): string {
  const parts = [`${result.matched} of ${result.expected_words} words heard as written`];
  if (result.substituted) parts.push(`${result.substituted} heard as something else`);
  if (result.missed) parts.push(`${result.missed} not heard`);
  if (result.added) {
    parts.push(`${result.added} heard that ${result.added === 1 ? "is" : "are"} not in the sentence`);
  }
  return `${parts.join(", ")}.`;
}

export function DrillResultView({ drill, result }: { drill: Drill; result: DrillResult }) {
  return (
    <section className="flex flex-col gap-4" aria-labelledby="drill-heard" aria-live="polite">
      <h2 id="drill-heard" className="text-base font-semibold">
        What the recogniser heard
      </h2>
      <ul className="flex flex-col gap-3">
        {result.verdicts.map((verdict) => (
          <Verdict key={verdict.id} verdict={verdict} drill={drill} />
        ))}
      </ul>
      <blockquote className="border-l-2 border-muted pl-3 text-sm italic">
        {result.heard || "Nothing was heard."}
      </blockquote>
      <Comparison words={result.words} />
      <p className="text-xs text-muted-foreground tabular-nums">{wordCounts(result)}</p>
    </section>
  );
}
