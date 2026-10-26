/**
 * What the Notebook says about a capture, and when: its other version, its state, the
 * day it belongs to in the reader's own zone, and when it comes back.
 */

import {
  byDay,
  comesBack,
  excerpt,
  keptEverywhere,
  otherVersion,
  stateLabel,
} from "@/lib/notebook";
import { dayKey, dayOf, knownZone, timeOf } from "@/lib/time";
import { makeCapture, makeCaptureSummary } from "@/test/fixtures";

test("the other version is the one of the pair that was not copied", () => {
  expect(otherVersion({ mode: "translate", chosen: "organized" })).toBe("direct");
  expect(otherVersion({ mode: "translate", chosen: "direct" })).toBe("organized");
  expect(otherVersion({ mode: "check", chosen: "corrected" })).toBe("polished");
  // The recogniser's rough English stood in for the model: Organized is what is owed.
  expect(otherVersion({ mode: "translate", chosen: "rough" })).toBe("organized");
});

test("a state is said the way the list says it", () => {
  expect(stateLabel("to_practise", 0)).toBe("To practise");
  expect(stateLabel("due", 2)).toBe("Due again");
  expect(stateLabel("practised", 1)).toBe("Practised once");
  expect(stateLabel("practised", 3)).toBe("Practised ×3");
});

test("a heading is the first words of what was said", () => {
  expect(excerpt("Laura, te escribo para avisarte que el informe del cliente se va")).toBe(
    "Laura, te escribo para avisarte que el informe…",
  );
  expect(excerpt("Hola Sofía.")).toBe("Hola Sofía");
});

test("captures are grouped by the reader's calendar day, not the server's", () => {
  // 21:30 UTC on the 24th is 01:30 on the 25th in Dubai.
  const late = makeCaptureSummary({ id: 1, created_at: "2026-10-24T21:30:00Z" });
  const early = makeCaptureSummary({ id: 2, created_at: "2026-10-24T08:00:00Z" });

  const inDubai = byDay([late, early], "Asia/Dubai");
  const inUtc = byDay([late, early], "UTC");

  expect(inDubai.map((day) => day.items.map((item) => item.id))).toEqual([[1], [2]]);
  expect(inDubai[0]!.label).toBe("Sunday 25 October");
  expect(inUtc.map((day) => day.items.map((item) => item.id))).toEqual([[1, 2]]);
});

test("times are on the reader's clock, and an unknown zone falls back to the runtime's", () => {
  expect(timeOf("2026-10-25T05:12:00Z", "Asia/Dubai")).toBe("09:12");
  expect(dayOf("2026-10-25T05:12:00Z", "Asia/Dubai")).toBe("Sunday 25 October");
  expect(dayKey("2026-10-25T21:00:00Z", "Asia/Dubai")).toBe("2026-10-26");
  expect(knownZone("Not/AZone")).toBeUndefined();
});

test("when it comes back is counted in calendar days", () => {
  const now = new Date("2026-10-25T10:00:00Z");
  expect(comesBack("2026-10-25T23:00:00Z", "UTC", now)).toBe("today");
  expect(comesBack("2026-10-26T09:00:00Z", "UTC", now)).toBe("tomorrow");
  expect(comesBack("2026-10-28T09:00:00Z", "UTC", now)).toBe("in 3 days");
});

test("what was kept everywhere leaves out anything a version dropped", () => {
  const capture = makeCapture({ dropped: { organized: [], direct: ["Acme"] } });

  expect(keptEverywhere(capture)).toEqual(["Laura", "14"]);
});
