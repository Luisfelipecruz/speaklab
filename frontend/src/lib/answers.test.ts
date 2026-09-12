/**
 * The arithmetic the answer pages share: where the marks go, how a clock reads, and the
 * rows two answers are compared on.
 */

import { answeredLabel, clock, compareRows, segments } from "@/lib/answers";
import { makeAnswer } from "@/test/fixtures";

test("the transcript is cut into plain and counted stretches, in order", () => {
  const text = "It failed because of a field. In short, a field.";
  const pieces = segments(text, [
    { kind: "close", start: 30, end: 38, text: "In short" },
    { kind: "reason", start: 10, end: 20, text: "because of" },
  ]);

  expect(pieces.map((piece) => piece.kind)).toEqual([null, "reason", null, "close", null]);
  expect(pieces.map((piece) => piece.text).join("")).toBe(text);
});

test("a mark that overlaps one already placed, or runs off the end, is left as text", () => {
  const text = "We we rolled back.";
  const pieces = segments(text, [
    { kind: "repeat", start: 0, end: 5, text: "We we" },
    { kind: "reason", start: 3, end: 8, text: "we ro" },
    { kind: "close", start: 10, end: 99, text: "?" },
  ]);

  expect(pieces.filter((piece) => piece.kind)).toHaveLength(1);
  expect(pieces.map((piece) => piece.text).join("")).toBe(text);
});

test("a clock reads minutes and seconds", () => {
  expect(clock(72_400)).toBe("1:12");
  expect(clock(90_000)).toBe("1:30");
  expect(clock(0)).toBe("0:00");
  expect(clock(null)).toBe("—");
});

test("two answers are compared on the same counts, and hidden measures are left out", () => {
  const first = makeAnswer();
  const second = makeAnswer({
    id: 8,
    again_of: 7,
    delivery: { ...first.delivery, words: 12, duration_ms: 7000 },
    structure: { ...first.structure, repeats: 0, sentences: 2, words_per_sentence: 6 },
  });

  const rows = compareRows(first, second);

  expect(rows.find((row) => row.label === "words")).toEqual({ label: "words", first: "18", second: "12" });
  expect(rows.find((row) => row.label === "said twice")).toEqual({
    label: "said twice",
    first: "1",
    second: "0",
  });
  expect(rows.find((row) => row.label === "length")?.second).toBe("0:07");

  const hidden = compareRows(
    { ...first, structure: { ...first.structure, repeats: null, sentences: null } },
    second,
  );
  expect(hidden.map((row) => row.label)).not.toContain("said twice");
  expect(hidden.map((row) => row.label)).not.toContain("sentences");
});

test("how often a question was answered reads as words", () => {
  expect(answeredLabel(0)).toBe("not answered yet");
  expect(answeredLabel(1)).toBe("answered once");
  expect(answeredLabel(2)).toBe("answered twice");
  expect(answeredLabel(5)).toBe("answered 5 times");
});
