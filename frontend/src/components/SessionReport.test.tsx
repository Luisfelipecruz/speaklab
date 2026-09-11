/**
 * The report, and its provenance split rendered as three headings.
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
import userEvent from "@testing-library/user-event";

import { SessionReport } from "@/components/SessionReport";
import { makeAnalysis, makeReport } from "@/test/fixtures";

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

test("the analyses nothing has produced are listed rather than omitted", () => {
  render(<SessionReport report={makeReport()} />);

  expect(screen.getByText("Not measured yet")).toBeInTheDocument();
  expect(screen.getByText(/Per-phoneme GOP/)).toBeInTheDocument();
});

test("fluency separates speech rate from articulation rate", () => {
  // The two are on screen together because a speaker who gets faster only by pausing
  // less has not learned to articulate any faster, and one number reports that as
  // progress.
  render(<SessionReport report={makeReport()} />);

  expect(screen.getByText("How you spoke")).toBeInTheDocument();
  expect(screen.getByText("118")).toBeInTheDocument();
  expect(screen.getByText("141")).toBeInTheDocument();
  expect(screen.getByText("16%")).toBeInTheDocument();
});

test("a declared form that was never used is shown as not used", () => {
  // The whole point of counting forms rather than only errors: a learner reaches a zero
  // error rate by only ever using the present simple.
  render(<SessionReport report={makeReport()} />);

  expect(screen.getByText("present perfect")).toBeInTheDocument();
  expect(screen.getByText(/conditional 2 — not used/)).toBeInTheDocument();
});

test("a correction shows what was said and what it should have been", () => {
  render(<SessionReport report={makeReport()} />);

  expect(screen.getByText("I complete the user story")).toBeInTheDocument();
  expect(screen.getByText("I completed the user story")).toBeInTheDocument();
  expect(screen.getByText(/verb tense · missing past marker/)).toBeInTheDocument();
});

test("an error on words the recogniser was unsure of is shown and marked", () => {
  // Hiding it would leave the transcript with a hole in it; counting it would let a
  // mishearing move a number about the speaker.
  render(<SessionReport report={makeReport()} />);

  expect(screen.getByText("look at the apartment")).toBeInTheDocument();
  expect(screen.getByText("may be a mishearing")).toBeInTheDocument();
  expect(screen.getByText(/1 not counted — the recogniser was unsure/)).toBeInTheDocument();
});

test("a correction found by a grammar rule says so, and one from the model does not", () => {
  const report = makeReport();
  const [first, second] = report.analysis!.errors.items;
  render(
    <SessionReport
      report={{
        ...report,
        analysis: {
          ...report.analysis!,
          errors: {
            ...report.analysis!.errors,
            items: [
              { ...first, detector: "rule" },
              { ...second, detector: "llm" },
            ],
            by_detector: { llm: 1, rule: 1 },
          },
        },
      }}
    />,
  );

  expect(screen.getAllByText("grammar rule")).toHaveLength(1);
});

test("once the rules exist, the report says they make the category split uneven", () => {
  // A layer that covers two categories finds those two more reliably than the model finds
  // the rest, so the split by category is partly a property of the detector.
  const report = makeReport();
  render(
    <SessionReport
      report={{
        ...report,
        analysis: {
          ...report.analysis!,
          errors: { ...report.analysis!.errors, by_detector: { llm: 2 } },
        },
      }}
    />,
  );

  expect(screen.getByText(/rules cover only agreement and missing articles/)).toBeInTheDocument();
});

test("a report written before the rules existed does not mention them", () => {
  // Reports are stored once. Saying the rules were applied to a session they never saw
  // would be a claim about it that is not true.
  render(<SessionReport report={makeReport()} />);

  expect(screen.queryByText(/rules cover only/)).not.toBeInTheDocument();
  expect(screen.queryByText("grammar rule")).not.toBeInTheDocument();
});

test("a report written before its turns were analysed says how many are missing", () => {
  const report = makeReport();
  render(
    <SessionReport
      report={{
        ...report,
        analysis: {
          ...report.analysis!,
          complete: false,
          turns_analysed: 4,
          turns_outstanding: 2,
        },
      }}
    />,
  );

  expect(
    screen.getByText(/2 of your turns had not been analysed when this report was written/),
  ).toBeInTheDocument();
  // Nothing on this screen can finish it, so nothing offers to.
  expect(screen.queryByRole("button", { name: "Finish the report" })).not.toBeInTheDocument();
});

test("an unfinished report offers to finish itself", async () => {
  const onFinish = jest.fn();
  render(
    <SessionReport
      report={makeReport({ analysis: makeAnalysis({ complete: false, turns_outstanding: 1 }) })}
      onFinish={onFinish}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Finish the report" }));
  expect(onFinish).toHaveBeenCalledTimes(1);
});

test("while the report is being finished it says so and offers nothing twice", () => {
  render(
    <SessionReport
      report={makeReport({ analysis: makeAnalysis({ complete: false, turns_outstanding: 1 }) })}
      finishing
      onFinish={jest.fn()}
    />,
  );

  expect(screen.getByRole("status")).toHaveTextContent(/Finishing this report/);
  expect(screen.queryByRole("button", { name: "Finish the report" })).not.toBeInTheDocument();
});

test("a report from before the analysers existed still renders", () => {
  // Reports are stored as they were written. One from an earlier version carries no
  // analysis at all, and a screen that assumed the key would be a blank page.
  render(<SessionReport report={makeReport({ analysis: null })} />);

  expect(screen.getByText("Session report")).toBeInTheDocument();
  expect(screen.queryByText("How you spoke")).not.toBeInTheDocument();
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
