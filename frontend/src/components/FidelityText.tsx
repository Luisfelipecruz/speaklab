/**
 * The script against what was heard, word by word.
 *
 * **Four marks, and no colour that means good or bad.** A word said as written is plain;
 * one said differently shows the script's word struck through with what was heard after
 * it; one not heard at all is struck through; a word said that is not in the script sits
 * between the others in muted italics. That is the whole vocabulary, and the legend under
 * the text names every mark rather than expecting a reader to work it out.
 *
 * **A word the recogniser was unsure of is marked as such, not excused.** It is dotted
 * underneath, and it says why on hover: a difference at a word the recogniser doubted is
 * the likeliest place for a mistake that is the microphone's rather than the speaker's.
 * Dropping those words from the comparison would quietly improve the noisiest takes.
 */

import type { AlignedWord } from "@/lib/api";

const UNSURE_TITLE = "The recogniser was not sure it heard this word.";

export interface FidelityTextProps {
  words: AlignedWord[];
}

export function FidelityText({ words }: FidelityTextProps) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-lg leading-relaxed" data-testid="fidelity-text">
        {words.map((word, index) => (
          <Word key={index} word={word} />
        ))}
      </p>
      <ul className="flex flex-wrap gap-4 text-xs text-muted-foreground" aria-label="What the marks mean">
        <li>plain — said as written</li>
        <li>
          <s>struck through</s> — not heard
        </li>
        <li>
          <s>struck</s> then a word — said differently
        </li>
        <li className="italic">italic — said, not in the script</li>
      </ul>
    </div>
  );
}

function Word({ word }: { word: AlignedWord }) {
  const unsure = word.unsure ? "underline decoration-dotted underline-offset-4" : "";
  const title = word.unsure ? UNSURE_TITLE : undefined;

  if (word.kind === "match") {
    return (
      <span className={unsure} title={title}>
        {word.expected}{" "}
      </span>
    );
  }

  if (word.kind === "deletion") {
    return (
      <span className="text-muted-foreground line-through" title="Not heard in this take.">
        {word.expected}{" "}
      </span>
    );
  }

  if (word.kind === "insertion") {
    return (
      <span className={`italic text-muted-foreground ${unsure}`} title={title ?? "Said, but not in the script."}>
        {word.heard}{" "}
      </span>
    );
  }

  return (
    <span title={title ?? "Said differently."}>
      <s className="text-muted-foreground">{word.expected}</s>{" "}
      <span className={`font-medium ${unsure}`}>{word.heard}</span>{" "}
    </span>
  );
}
