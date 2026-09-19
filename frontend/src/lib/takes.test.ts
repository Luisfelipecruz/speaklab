/**
 * The sentence a take gets, assembled from its own counts.
 *
 * The rules being tested are the ones that keep it honest: it says nothing when there is
 * nothing to say, it invents no comparison from a single take, and it never calls a take
 * good or bad — the words it is allowed to use are about numbers moving, not about the
 * person who recorded it.
 */

import type { AlignedWord, Take } from "@/lib/api";
import { before, earlierThan, takeSentence } from "@/lib/takes";
import { makeTake } from "@/test/fixtures";

function differing(kinds: AlignedWord["kind_of_difference"][]): AlignedWord[] {
  return kinds.map((kind_of_difference, index) => ({
    kind: "substitution",
    expected: `word${index}`,
    heard: `heard${index}`,
    unsure: false,
    kind_of_difference,
  }));
}

function take(id: number, fields: Partial<Take> = {}, kinds: AlignedWord["kind_of_difference"][] = []): Take {
  const base = makeTake({ id, ...fields });
  return { ...base, fidelity: { ...base.fidelity, words: differing(kinds) } };
}

test("one take says what it contains and compares itself with nothing", () => {
  const only = take(9, { speech_rate_wpm: 85 }, ["ending", "ending", "different-word"]);

  expect(takeSentence(only, [only])).toBe("Most of the differences are endings.");
});

test("a second take names the direction the pace moved, and by how much", () => {
  const latest = take(9, { wer: 0.2, speech_rate_wpm: 85 }, ["ending", "ending"]);
  const first = take(8, { wer: 0.1, speech_rate_wpm: 91 });

  expect(takeSentence(latest, [latest, first])).toBe(
    "Most of the differences are endings; slower than your last take by 6 words a minute.",
  );
});

test("the closest take yet to the script is said to be so, counting from the takes", () => {
  const latest = take(9, { wer: 0.1, speech_rate_wpm: 85 }, ["ending"]);
  const first = take(8, { wer: 0.3, speech_rate_wpm: 85 });

  expect(takeSentence(latest, [latest, first])).toBe(
    "Closest yet to your script; most of the differences are endings.",
  );
});

test("a take further from the script than the last one is not told so", () => {
  const latest = take(9, { wer: 0.4, speech_rate_wpm: 85 });
  const first = take(8, { wer: 0.1, speech_rate_wpm: 85 });

  expect(takeSentence(latest, [latest, first])).toBeNull();
});

test("no sentence is invented for a take with nothing to report", () => {
  const only = take(9, { speech_rate_wpm: null });

  expect(takeSentence(only, [only])).toBeNull();
});

test("an even split between the kinds names neither as the larger", () => {
  const only = take(9, {}, ["ending", "different-word"]);

  expect(takeSentence(only, [only])).toBeNull();
});

test("a pace that did not move is not mentioned", () => {
  const latest = take(9, { wer: 0.2, speech_rate_wpm: 85.2 }, ["ending"]);
  const first = take(8, { wer: 0.2, speech_rate_wpm: 85.4 });

  expect(takeSentence(latest, [latest, first])).toBe(
    "Closest yet to your script; most of the differences are endings.",
  );
});

test("nothing it can say is about the speaker rather than the numbers", () => {
  const latest = take(9, { wer: 0.1, speech_rate_wpm: 70 }, ["different-word"]);
  const first = take(8, { wer: 0.3, speech_rate_wpm: 95 });

  const sentence = takeSentence(latest, [latest, first]) ?? "";

  for (const verdict of ["better", "worse", "good", "bad", "well", "poor", "improved"]) {
    expect(sentence).not.toContain(verdict);
  }
});

test("the take before, and the takes before that, are found in a list newest first", () => {
  const third = take(9);
  const second = take(8);
  const first = take(7);
  const takes = [third, second, first];

  expect(before(takes, third)).toBe(second);
  expect(before(takes, first)).toBeNull();
  expect(earlierThan(takes, third)).toEqual([second, first]);
  expect(earlierThan(takes, first)).toEqual([]);
});
