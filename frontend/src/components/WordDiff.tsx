/**
 * Two texts aligned word by word: where one differs from the other, and how.
 *
 * Plain code did the aligning, the same edit distance the recogniser is measured with, so
 * a difference here is a difference in words and never a judgement: the version may be
 * the worse English. A word only in the version is struck through, a word only in the
 * person's text is underlined, and a changed word shows both.
 */

import { cn } from "@/lib/utils";

export interface Step {
  expected: string | null;
  /** The person's word: what they wrote, or what was heard when they said it. */
  theirs: string | null;
}

export function WordDiff({ steps, label }: { steps: Step[]; label: string }) {
  const changed = steps.filter((step) => step.expected !== step.theirs).length;
  return (
    <figure className="flex flex-col gap-2">
      <p className="text-base leading-8" aria-label={label} data-testid="word-diff">
        {steps.map((step, index) => {
          const same = step.expected === step.theirs;
          return (
            <span key={index}>
              {index > 0 && " "}
              {same ? (
                <span>{step.theirs}</span>
              ) : (
                <span className="inline-flex gap-1">
                  {step.expected && (
                    <del
                      className={cn(
                        "text-muted-foreground decoration-muted-foreground",
                        step.theirs && "decoration-1",
                      )}
                    >
                      <span className="sr-only">the version has </span>
                      {step.expected}
                    </del>
                  )}
                  {step.theirs && (
                    <ins className="rounded-sm bg-chart-2/15 px-0.5 underline underline-offset-4">
                      <span className="sr-only">you have </span>
                      {step.theirs}
                    </ins>
                  )}
                </span>
              )}
            </span>
          );
        })}
      </p>
      <figcaption className="text-xs text-muted-foreground">
        {changed === 0
          ? "Word for word the same."
          : `${changed} word${changed === 1 ? "" : "s"} different. Struck through: only in the version; underlined: only in yours.`}
      </figcaption>
    </figure>
  );
}
