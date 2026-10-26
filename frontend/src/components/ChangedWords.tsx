/**
 * A version beside what the person said or wrote, word by word: a word of theirs the
 * version changed or dropped is struck through, and the version's word in its place is
 * marked.
 *
 * Plain code aligned the two, without case or punctuation, so a mark is a different word
 * and never a judgement: the version is a suggestion, and for Polished it is never counted.
 */

import type { WordChange } from "@/lib/api";

/** A word without case or punctuation, as the alignment compared it. */
function bare(word: string | null): string {
  return (word ?? "").toLowerCase().replace(/[^\p{L}\p{N}']+/gu, "");
}

export function ChangedWords({ steps }: { steps: WordChange[] }) {
  const changed = steps.filter((step) => bare(step.said) !== bare(step.version)).length;
  if (changed === 0) return null;
  return (
    <figure className="flex flex-col gap-1.5" data-testid="changed-words">
      <p className="max-w-[64ch] text-sm leading-7 text-muted-foreground">
        {steps.map((step, index) => {
          const same = bare(step.said) === bare(step.version);
          return (
            <span key={index}>
              {index > 0 && " "}
              {same ? (
                <span>{step.version}</span>
              ) : (
                <span className="inline-flex gap-1">
                  {step.said && (
                    <del className="decoration-muted-foreground">
                      <span className="sr-only">you had </span>
                      {step.said}
                    </del>
                  )}
                  {step.version && (
                    <ins className="rounded-sm bg-chart-2/15 px-0.5 text-foreground no-underline">
                      <span className="sr-only">this version has </span>
                      {step.version}
                    </ins>
                  )}
                </span>
              )}
            </span>
          );
        })}
      </p>
      <figcaption className="text-xs text-muted-foreground">
        {changed} word{changed === 1 ? "" : "s"} changed from yours: yours struck through, this
        version&rsquo;s marked.
      </figcaption>
    </figure>
  );
}
