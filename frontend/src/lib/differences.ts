/**
 * The three kinds a word said differently can be, named once for every screen that
 * shows them.
 *
 * The colours tell the kinds apart and say nothing about how well anybody did: there is
 * no good one and no bad one among them. Nothing is carried by colour alone either —
 * every mark keeps its strike-through, and every word says its kind in words on hover —
 * because a reader who cannot see the difference between two tints still has to be able
 * to read the screen.
 */

import type { AlignedWord, DifferenceKind } from "@/lib/api";

export const DIFFERENCE_TINT: Record<DifferenceKind, string> = {
  ending: "text-chart-1",
  "different-word": "text-chart-4",
  figure: "text-muted-foreground",
};

/** What one word of this kind is, said to the person who recorded it. */
export const DIFFERENCE_TITLE: Record<DifferenceKind, string> = {
  ending: "The same word with a different ending.",
  "different-word": "A different word.",
  figure: "The same number, written as a figure. Not counted as a difference.",
};

/** The heading a group of them sits under. */
export const DIFFERENCE_HEADING: Record<DifferenceKind, string> = {
  ending: "Endings",
  "different-word": "Other words",
  figure: "Numbers written as figures",
};

/** Why the group is a group, in one line. */
export const DIFFERENCE_NOTE: Record<DifferenceKind, string> = {
  ending:
    "The word is there and its end is not: a plural, a tense, a comparative, a contraction.",
  "different-word":
    "A different word came out. It may be what you said, or what the recogniser heard.",
  figure:
    "You said the number and the recogniser wrote it as a digit. Not counted against you.",
};

/** The order the groups are read in: what you can work on first, what is not yours last. */
export const DIFFERENCE_ORDER: DifferenceKind[] = ["ending", "different-word", "figure"];

export function countOfKind(words: AlignedWord[], kind: DifferenceKind): number {
  return wordsOfKind(words, kind).length;
}

export function wordsOfKind(words: AlignedWord[], kind: DifferenceKind): AlignedWord[] {
  return words.filter(
    (word) => word.kind === "substitution" && word.kind_of_difference === kind,
  );
}

/**
 * "2 endings and 3 other words", or null when nothing was said differently.
 *
 * Figures are left out of this sentence on purpose: they are not differences, and the
 * group that lists them says so itself.
 */
export function differenceSentence(words: AlignedWord[]): string | null {
  const endings = countOfKind(words, "ending");
  const others = countOfKind(words, "different-word");
  const counted = endings + others;
  if (counted === 0) return null;

  const parts: string[] = [];
  if (endings > 0) parts.push(`${endings} ${endings === 1 ? "ending" : "endings"}`);
  if (others > 0) parts.push(`${others} other ${others === 1 ? "word" : "words"}`);

  const head = `${counted} ${counted === 1 ? "word" : "words"} came out differently`;
  return `${head} — ${parts.join(" and ")}.`;
}
