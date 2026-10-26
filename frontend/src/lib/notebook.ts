/**
 * What the Notebook says about a capture, in words: its versions, its state, where it is
 * in the practice schedule, and its fixes in the shape the transcript marker reads.
 */

import type {
  Capture,
  CaptureFix,
  CaptureState,
  CaptureSummary,
  CaptureVersion,
  LanguageErrorItem,
} from "@/lib/api";
import { dayKey, dayOf, daysUntil } from "@/lib/time";

export const VERSION_LABEL: Record<CaptureVersion, string> = {
  organized: "Organized",
  direct: "Direct",
  corrected: "Corrected",
  polished: "Polished",
  rough: "Rough",
};

/** What each version is, in one line, for the place where both are side by side. */
export const VERSION_HINT: Record<CaptureVersion, string> = {
  organized: "Written English for where it is going, the ideas in order.",
  direct: "Your words in English, in your order and your tone.",
  corrected: "Your words, with the spelling and grammar fixed.",
  polished: "Rewritten for clarity and tone.",
  rough: "The recogniser's own English, rough and literal.",
};

/** The pair a capture offers, the default first. */
export function offered(mode: Capture["mode"]): [CaptureVersion, CaptureVersion] {
  return mode === "translate" ? ["organized", "direct"] : ["corrected", "polished"];
}

/** The version that was not copied, if the capture has one. */
export function otherVersion(capture: Pick<Capture, "mode" | "chosen">): CaptureVersion {
  const [first, second] = offered(capture.mode);
  return capture.chosen === first ? second : first;
}

export function stateLabel(state: CaptureState, practised: number): string {
  if (state === "to_practise") return "To practise";
  if (state === "due") return "Due again";
  return practised === 1 ? "Practised once" : `Practised ×${practised}`;
}

export function howLabel(capture: Pick<Capture, "via" | "mode">): string {
  const how = capture.via === "voice" ? "Said" : capture.via === "typed" ? "Typed" : "Copied";
  return capture.mode === "check" ? `${how} in English, checked` : how;
}

/** The first words of what was said, for a heading. */
export function excerpt(text: string, words = 8): string {
  const all = text.trim().split(/\s+/);
  const cut = all.slice(0, words).join(" ").replace(/[,;:.]+$/, "");
  return all.length > words ? `${cut}…` : cut;
}

export interface Day<T> {
  key: string;
  label: string;
  items: T[];
}

/** Captures by the calendar day they were made, in the reader's zone, newest day first. */
export function byDay<T extends Pick<CaptureSummary, "created_at">>(items: T[], zone?: string): Day<T>[] {
  const days: Day<T>[] = [];
  for (const item of items) {
    const key = dayKey(item.created_at, zone);
    const last = days[days.length - 1];
    if (last && last.key === key) last.items.push(item);
    else days.push({ key, label: dayOf(item.created_at, zone), items: [item] });
  }
  return days;
}

/** When a capture comes back, in words: "tomorrow", "in 3 days", "today". */
export function comesBack(dueAt: string, zone?: string, now: Date = new Date()): string {
  const days = daysUntil(dueAt, zone, now);
  if (days <= 0) return "today";
  if (days === 1) return "tomorrow";
  return `in ${days} days`;
}

/** A fix in the shape the transcript marker reads: placed by its span, counted or not. */
export function asMarked(fix: CaptureFix): LanguageErrorItem {
  return {
    turn_id: 0,
    category: fix.category,
    subcategory: fix.subcategory,
    span_start: fix.span_start,
    span_end: fix.span_end,
    original: fix.original,
    correction: fix.correction,
    explanation: fix.explanation,
    confidence: 1,
    asr_suspect: false,
    counted: fix.counted,
    detector: fix.detector === "dictionary" ? undefined : fix.detector,
  };
}

/** Which detector found a fix, as the list under the text names it. */
export function sourceOf(fix: CaptureFix): string {
  if (fix.detector === "dictionary") return "dictionary";
  if (fix.detector === "rule") return "grammar rule";
  return "language model";
}

/** Everything every version had to keep and did, for "Kept in both versions". */
export function keptEverywhere(capture: Pick<Capture, "kept" | "dropped">): string[] {
  const lost = new Set(Object.values(capture.dropped).flat());
  return capture.kept.filter((item) => !lost.has(item));
}
