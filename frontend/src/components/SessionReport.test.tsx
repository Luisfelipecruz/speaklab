/**
 * The report, and invariant I1 rendered as three headings.
 *
 * The report arrives already split by where each number came from, and the only job this
 * component has is to keep that split on screen. So the tests are mostly about
 * provenance: the counted figures are under a heading that says they were counted, the
 * prose is under one that says a model wrote it and names the model, and the analyses
 * that do not exist yet are listed rather than quietly omitted.
 *
 * The last one is not pedantry. A report that drops its "errors" section because there
 * is no analyser reads exactly like a session that contained no errors.
 */

import { render, screen } from "@testing-library/react";

import { SessionReport } from "@/components/SessionReport";
import { makeReport } from "@/test/fixtures";

test("the counted figures are presented as counted", () => {
  render(<SessionReport report={makeReport()} />);

  expect(screen.getByText("Counted from this session")).toBeInTheDocument();
  expect(screen.getByText(/same numbers\s+every time/)).toBeInTheDocument();
  expect(screen.getByText("318")).toBeInTheDocument();
  expect(screen.getByText("6")).toBeInTheDocument();
  expect(screen.getByText("2.4s")).toBeInTheDocument();
  expect(screen.getByText("4m 5s")).toBeInTheDocument();
});

test("the prose is attributed to the model that wrote it", () => {
  render(<SessionReport report={makeReport()} />);

  expect(screen.getByText("Written by the language model")).toBeInTheDocument();
  expect(screen.getByText(/by gemma3:4b/)).toBeInTheDocument();
  // I1, said out loud on the screen and not only in a docstring.
  expect(screen.getByText(/nothing here is plotted over time/)).toBeInTheDocument();
  expect(screen.getByText(/defended the schedule twice/)).toBeInTheDocument();
});

test("a goal judgement is labelled as the model's, not stated as fact", () => {
  render(<SessionReport report={makeReport()} />);

  expect(screen.getByText("the model judged the goal met")).toBeInTheDocument();
});

test("a model that was down leaves the counted figures untouched and says why", () => {
  render(
    <SessionReport
      report={makeReport({
        narrative: { status: "unavailable", detail: "LlmUnavailable: connection refused" },
      })}
    />,
  );

  expect(screen.getByText(/was not available when this session ended/)).toBeInTheDocument();
  expect(screen.getByText(/counted figures above are unaffected/)).toBeInTheDocument();
  expect(screen.getByText("318")).toBeInTheDocument();
});

test("a model that ignored the format is reported as that, not salvaged", () => {
  render(<SessionReport report={makeReport({ narrative: { status: "unparseable" } })} />);

  expect(screen.getByText(/did not answer in the format/)).toBeInTheDocument();
});

test("the analyses that do not exist yet are listed with the milestone that builds them", () => {
  render(<SessionReport report={makeReport()} />);

  expect(screen.getByText("Not measured yet")).toBeInTheDocument();
  expect(screen.getByText(/m9 — the closed taxonomy/)).toBeInTheDocument();
  expect(screen.getByText(/m8 — per-phoneme GOP/)).toBeInTheDocument();
});

test("a session short of its rubric minimum says so plainly", () => {
  const report = makeReport();
  render(
    <SessionReport
      report={{
        ...report,
        measured: { ...report.measured, turns: { total: 4, user: 2, assistant: 2 }, reached_min_turns: false },
      }}
    />,
  );

  expect(screen.getByText("short of the 6-turn minimum")).toBeInTheDocument();
});
