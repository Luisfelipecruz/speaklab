/**
 * One take read against the ones before it, in a sentence assembled from the counts.
 *
 * Everything here is arithmetic over numbers already on the page. No model writes any of
 * it, nothing is stored, and nothing says whether the speaker did well: the sentence
 * names the largest group of differences, says which way the pace moved against their own
 * last take, and stops. "Closest yet to your script" is a statement about a count, not a
 * compliment, and there is deliberately no sentence for the opposite — a take further
 * from the script than the last one is a normal part of rehearsing something and does not
 * need pointing out.
 *
 * With one take there is nothing to compare with, so the sentence says only what this
 * take contains. A screen that invented a comparison from a single reading would be
 * making a trend out of a point.
 */

import type { AlignedWord, Take } from "@/lib/api";
import { countOfKind } from "@/lib/differences";

/**
 * The take of this section before the one being looked at.
 *
 * The list is newest first, so the one before is the next along. The only comparison that
 * means anything here is the speaker against themselves: there is no corpus of good
 * presentations behind this product and no norm it could hold anybody to.
 */
export function before(takes: Take[], shown: Take): Take | null {
  const at = takes.findIndex((take) => take.id === shown.id);
  return at === -1 ? null : (takes[at + 1] ?? null);
}

/** The takes of this section recorded before the one shown, newest first. */
export function earlierThan(takes: Take[], shown: Take): Take[] {
  const at = takes.findIndex((take) => take.id === shown.id);
  return at === -1 ? [] : takes.slice(at + 1);
}

function largestGroup(words: AlignedWord[]): string | null {
  const endings = countOfKind(words, "ending");
  const others = countOfKind(words, "different-word");
  if (endings === 0 && others === 0) return null;
  if (endings === others) return null;
  return endings > others
    ? "most of the differences are endings"
    : "most of the differences are other words";
}

function pace(take: Take, previous: Take | null): string | null {
  if (!previous || take.speech_rate_wpm === null || previous.speech_rate_wpm === null) {
    return null;
  }
  const moved = Math.round(take.speech_rate_wpm) - Math.round(previous.speech_rate_wpm);
  if (moved === 0) return null;
  const direction = moved > 0 ? "faster" : "slower";
  return `${direction} than your last take by ${Math.abs(moved)} words a minute`;
}

/**
 * What this take was, in one sentence, or null when there is nothing to say about it.
 *
 * `takes` is every take of the section, newest first, including this one.
 */
export function takeSentence(take: Take, takes: Take[]): string | null {
  const previous = before(takes, take);
  const earlier = earlierThan(takes, take);

  const parts: string[] = [];
  if (earlier.length > 0 && earlier.every((other) => take.wer <= other.wer)) {
    parts.push("closest yet to your script");
  }

  const group = largestGroup(take.fidelity.words);
  if (group) parts.push(group);

  const moved = pace(take, previous);
  if (moved) parts.push(moved);

  if (parts.length === 0) return null;
  return `${parts[0][0].toUpperCase()}${parts[0].slice(1)}${
    parts.length > 1 ? `; ${parts.slice(1).join("; ")}` : ""
  }.`;
}
