/**
 * Where a correction sits in the words it is about.
 *
 * Every correction the analysis stores carries character offsets into the transcript of
 * the turn it was found in. Until now the only screen that read them was the report at
 * the end, which listed the corrections in a block under the conversation and left the
 * transcript itself unmarked — so a learner could read that "look department" should
 * have been "look at the apartment" and still have to scroll up and hunt for the turn.
 * This module turns those offsets into segments a bubble can render in place.
 *
 * **The transcript's words win, not the correction's.** The offsets were found by a
 * case-insensitive, whitespace-tolerant search, so the stored quote can differ from the
 * words at its offsets in capitalisation and spacing. The check here compares letters
 * and digits only, the same normalisation the server used. A correction whose offsets
 * do not hold the words it quotes is still listed, but nothing is underlined: an
 * underline under the wrong words is a correction pointing at something the speaker
 * got right, which is worse than no underline at all.
 *
 * **Overlaps are not nested.** Two corrections can be accepted for overlapping stretches
 * of one turn. The first by position is marked; the later one is listed under the bubble
 * with a number and no mark. Nested marks would need markup that reads as one word
 * belonging to two corrections, and the list says the same thing more plainly.
 */

import type { LanguageErrorItem, SessionReportShape } from "@/lib/api";

export interface NumberedCorrection {
  item: LanguageErrorItem;
  /** 1-based, in the order the list under the bubble shows them. */
  number: number;
  /** False when the correction is listed but its words are not marked. */
  placed: boolean;
}

export interface Segment {
  text: string;
  /** Null for plain text between corrections. */
  correction: NumberedCorrection | null;
}

export interface MarkedTranscript {
  segments: Segment[];
  corrections: NumberedCorrection[];
}

/** Corrections keyed by the turn they were found in. Empty for a report with no analysis. */
export function correctionsByTurn(
  report: SessionReportShape | null | undefined,
): Map<number, LanguageErrorItem[]> {
  const byTurn = new Map<number, LanguageErrorItem[]>();
  for (const item of report?.analysis?.errors.items ?? []) {
    const list = byTurn.get(item.turn_id);
    if (list) {
      list.push(item);
    } else {
      byTurn.set(item.turn_id, [item]);
    }
  }
  return byTurn;
}

/** Letters and digits only, lowercased: what was said, without how it was written down. */
function bare(text: string): string {
  return text.replace(/[^\p{L}\p{N}]+/gu, "").toLowerCase();
}

function holdsItsWords(transcript: string, item: LanguageErrorItem): boolean {
  const { span_start: start, span_end: end } = item;
  if (start === null || end === null) return false;
  if (!Number.isInteger(start) || !Number.isInteger(end)) return false;
  if (start < 0 || end > transcript.length || start >= end) return false;
  return bare(transcript.slice(start, end)) === bare(item.original);
}

/**
 * The transcript cut into plain stretches and marked ones, plus every correction
 * numbered in the order the bubble lists them: marked ones first in text order, then
 * the ones that could not be marked, in the order the report gave them.
 */
export function markTranscript(
  transcript: string,
  items: LanguageErrorItem[],
): MarkedTranscript {
  const placeable = items
    .filter((item) => holdsItsWords(transcript, item))
    .sort((a, b) => (a.span_start as number) - (b.span_start as number));

  const placed: LanguageErrorItem[] = [];
  let reach = 0;
  for (const item of placeable) {
    if ((item.span_start as number) >= reach) {
      placed.push(item);
      reach = item.span_end as number;
    }
  }

  const corrections: NumberedCorrection[] = [];
  for (const item of placed) {
    corrections.push({ item, number: corrections.length + 1, placed: true });
  }
  for (const item of items) {
    if (!placed.includes(item)) {
      corrections.push({ item, number: corrections.length + 1, placed: false });
    }
  }

  const segments: Segment[] = [];
  let cursor = 0;
  for (const correction of corrections) {
    if (!correction.placed) break;
    const start = correction.item.span_start as number;
    const end = correction.item.span_end as number;
    if (start > cursor) segments.push({ text: transcript.slice(cursor, start), correction: null });
    segments.push({ text: transcript.slice(start, end), correction });
    cursor = end;
  }
  if (cursor < transcript.length) {
    segments.push({ text: transcript.slice(cursor), correction: null });
  }

  return { segments, corrections };
}
