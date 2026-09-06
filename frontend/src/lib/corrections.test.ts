/**
 * Placing a correction on the words it is about, and refusing to when it cannot.
 *
 * The one property under test is that a mark never lands on words the correction did
 * not quote. Everything else — numbering, grouping — follows from it.
 */

import { correctionsByTurn, markTranscript } from "@/lib/corrections";
import type { LanguageErrorItem } from "@/lib/api";
import { makeAnalysis, makeReport } from "@/test/fixtures";

const TRANSCRIPT = "Yesterday I complete the user story and I have send it to the tester.";

/** The offsets of `quote` in `TRANSCRIPT`, computed rather than counted by hand. */
function at(quote: string): { span_start: number; span_end: number } {
  const span_start = TRANSCRIPT.indexOf(quote);
  if (span_start < 0) throw new Error(`"${quote}" is not in the transcript`);
  return { span_start, span_end: span_start + quote.length };
}

function item(overrides: Partial<LanguageErrorItem> = {}): LanguageErrorItem {
  return {
    turn_id: 6,
    category: "VERB_TENSE",
    subcategory: "missing_past_marker",
    ...at("I complete the user story"),
    original: "I complete the user story",
    correction: "I completed the user story",
    explanation: "Yesterday needs the past simple.",
    confidence: 0.9,
    asr_suspect: false,
    counted: true,
    ...overrides,
  };
}

test("corrections are grouped by the turn they were found in", () => {
  const byTurn = correctionsByTurn(makeReport({ analysis: makeAnalysis() }));

  expect([...byTurn.keys()]).toEqual([6, 8]);
  expect(byTurn.get(6)).toHaveLength(1);
  expect(byTurn.get(8)?.[0].original).toBe("look department");
});

test("a report without analysis yields nothing rather than throwing", () => {
  expect(correctionsByTurn(makeReport({ analysis: null })).size).toBe(0);
  expect(correctionsByTurn(null).size).toBe(0);
});

test("the quoted words are marked, in text order, and numbered the same way", () => {
  const later = item({
    ...at("I have send"),
    original: "I have send",
    correction: "I sent",
    category: "VERB_TENSE",
  });
  const marked = markTranscript(TRANSCRIPT, [later, item()]);

  expect(marked.segments.map((s) => s.text)).toEqual([
    "Yesterday ",
    "I complete the user story",
    " and ",
    "I have send",
    " it to the tester.",
  ]);
  expect(marked.segments.map((s) => s.correction?.number ?? null)).toEqual([
    null,
    1,
    null,
    2,
    null,
  ]);
  expect(marked.corrections.map((c) => c.item.original)).toEqual([
    "I complete the user story",
    "I have send",
  ]);
});

test("the transcript's own spelling is kept where it differs from the quote", () => {
  // The offsets were found case-insensitively, so the stored quote can carry the
  // model's capitalisation. What is marked is what the recogniser wrote down.
  const marked = markTranscript("yesterday i  complete the story", [
    item({ span_start: 10, span_end: 31, original: "I complete the story" }),
  ]);

  expect(marked.segments[1]).toMatchObject({ text: "i  complete the story" });
  expect(marked.corrections[0].placed).toBe(true);
});

test("offsets that do not hold the quoted words are listed and never marked", () => {
  const marked = markTranscript(TRANSCRIPT, [item({ span_start: 0, span_end: 9 })]);

  expect(marked.segments).toEqual([{ text: TRANSCRIPT, correction: null }]);
  expect(marked.corrections).toEqual([
    expect.objectContaining({ number: 1, placed: false }),
  ]);
});

test("a correction with no offsets is listed without a mark", () => {
  const marked = markTranscript(TRANSCRIPT, [item({ span_start: null, span_end: null })]);

  expect(marked.segments).toHaveLength(1);
  expect(marked.corrections[0].placed).toBe(false);
});

test("a correction overlapping an earlier one is listed after it and not nested", () => {
  const overlapping = item({
    ...at("user story and I"),
    original: "user story and I",
    correction: "user story, and I",
    category: "WORD_ORDER",
  });
  const marked = markTranscript(TRANSCRIPT, [item(), overlapping]);

  expect(marked.segments.filter((s) => s.correction)).toHaveLength(1);
  expect(marked.corrections.map((c) => [c.number, c.placed])).toEqual([
    [1, true],
    [2, false],
  ]);
});

test("offsets past the end of the transcript are not trusted", () => {
  const marked = markTranscript("Short.", [item({ span_start: 2, span_end: 40 })]);

  expect(marked.segments).toEqual([{ text: "Short.", correction: null }]);
});
