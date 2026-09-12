/**
 * The words and the arithmetic the answer pages share, kept apart from the components so
 * each can be tested on its own.
 *
 * **What a signpost is called on screen.** The API names them by what they do — `reason`,
 * `example`, `sequence`, `contrast`, `close` — and the page says the same thing in the
 * words a learner would use: a reason, an example, a step, a contrast, summing up.
 */

import type { Counted, PromptCategory, SignpostKind, SpokenAnswer } from "@/lib/api";

export const SIGNPOSTS: readonly SignpostKind[] = [
  "reason",
  "example",
  "sequence",
  "contrast",
  "close",
];

export const KIND_LABEL: Record<Counted["kind"], string> = {
  reason: "a reason",
  example: "an example",
  sequence: "a step",
  contrast: "a contrast",
  close: "summing up",
  repeat: "said twice",
};

/** What each kind of signpost is, with the words that usually say it. */
export const KIND_HINT: Record<SignpostKind, string> = {
  reason: "because, so, that's why",
  example: "for example, such as",
  sequence: "first, then, after that",
  contrast: "but, however, although",
  close: "in short, overall, to sum up",
};

export const CATEGORY_LABEL: Record<PromptCategory, string> = {
  explain: "Explain what happened",
  justify: "Justify a choice",
  "walk-through": "Walk someone through it",
  recommend: "Recommend something",
};

export const CATEGORY_ORDER: readonly PromptCategory[] = [
  "explain",
  "justify",
  "walk-through",
  "recommend",
];

export interface Segment {
  text: string;
  kind: Counted["kind"] | null;
}

/**
 * The transcript cut into plain stretches and counted ones, in order.
 *
 * A counted stretch that overlaps one already placed, or that runs off the transcript, is
 * left as plain text rather than drawn wrong: the mark has to sit on the words it counts.
 */
export function segments(transcript: string, found: Counted[]): Segment[] {
  const pieces: Segment[] = [];
  let cursor = 0;
  for (const item of [...found].sort((a, b) => a.start - b.start || a.end - b.end)) {
    if (item.start < cursor || item.end > transcript.length || item.end <= item.start) {
      continue;
    }
    if (item.start > cursor) pieces.push({ text: transcript.slice(cursor, item.start), kind: null });
    pieces.push({ text: transcript.slice(item.start, item.end), kind: item.kind });
    cursor = item.end;
  }
  if (cursor < transcript.length) pieces.push({ text: transcript.slice(cursor), kind: null });
  return pieces;
}

/** Milliseconds as a clock: 72 400 → "1:12". */
export function clock(ms: number | null): string {
  if (ms === null) return "—";
  const seconds = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function figure(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return Number(value.toFixed(digits)).toString();
}

function percent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export interface CompareRow {
  label: string;
  first: string;
  second: string;
}

/**
 * The same counts for two answers to one prompt, as rows of text.
 *
 * No row says which side is better. A shorter answer is not always a clearer one, and an
 * answer with more signposts is not a better answer; the two are laid side by side and
 * read by the person who gave them.
 */
export function compareRows(first: SpokenAnswer, second: SpokenAnswer): CompareRow[] {
  const rows: CompareRow[] = [
    {
      label: "length",
      first: clock(first.delivery.duration_ms),
      second: clock(second.delivery.duration_ms),
    },
    { label: "words", first: figure(first.delivery.words), second: figure(second.delivery.words) },
    {
      label: "speech rate, wpm",
      first: figure(first.delivery.speech_rate_wpm),
      second: figure(second.delivery.speech_rate_wpm),
    },
    {
      label: "time spent paused",
      first: percent(first.delivery.pause_ratio),
      second: percent(second.delivery.pause_ratio),
    },
    {
      label: "fillers",
      first: figure(first.delivery.fillers),
      second: figure(second.delivery.fillers),
    },
  ];
  if (first.structure.sentences !== null && second.structure.sentences !== null) {
    rows.push(
      {
        label: "sentences",
        first: figure(first.structure.sentences),
        second: figure(second.structure.sentences),
      },
      {
        label: "words per sentence",
        first: figure(first.structure.words_per_sentence, 1),
        second: figure(second.structure.words_per_sentence, 1),
      },
    );
  }
  if (first.structure.repeats !== null && second.structure.repeats !== null) {
    rows.push({
      label: "said twice",
      first: figure(first.structure.repeats),
      second: figure(second.structure.repeats),
    });
  }
  for (const kind of SIGNPOSTS) {
    const a = first.structure.signposts[kind];
    const b = second.structure.signposts[kind];
    if (a === undefined || b === undefined) continue;
    rows.push({ label: KIND_LABEL[kind], first: figure(a), second: figure(b) });
  }
  return rows;
}

/** "answered twice", "not answered yet". */
export function answeredLabel(count: number): string {
  if (count === 0) return "not answered yet";
  if (count === 1) return "answered once";
  if (count === 2) return "answered twice";
  return `answered ${count} times`;
}
