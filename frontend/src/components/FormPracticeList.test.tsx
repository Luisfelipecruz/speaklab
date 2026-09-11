/**
 * The verb forms, as counts with the corrections behind them.
 *
 * The one assertion that matters most is the absence of a percentage: the API computes
 * one, and this list must not show it. The rest is that a form needed and never said is
 * listed, and that each count comes with the corrections a learner can check it against.
 */

import { render, screen, within } from "@testing-library/react";

import { FormPracticeList, formCount } from "@/components/FormPracticeList";
import { makeFormPractice } from "@/test/fixtures";

test("each form is a count with the corrections behind it", () => {
  render(<FormPracticeList forms={[makeFormPractice()]} />);

  const row = screen.getByTestId("form-present_simple");
  expect(within(row).getByText("right 11 of 12")).toBeInTheDocument();
  expect(within(row).getByText("said 12 times · corrected once")).toBeInTheDocument();
  expect(within(row).getByText("I completed the user story")).toBeInTheDocument();
});

test("no form is ever given a percentage", () => {
  render(
    <FormPracticeList
      forms={[makeFormPractice({ used: 40, right: 30, wrong: 10, missed: 5 })]}
    />,
  );

  expect(screen.getByText("right 30 of 45")).toBeInTheDocument();
  expect(screen.queryByText(/%/)).not.toBeInTheDocument();
});

test("a form needed and never said is listed, because avoiding it is the finding", () => {
  const avoided = makeFormPractice({
    form: "present_perfect",
    label: "present perfect",
    used: 0,
    right: 0,
    wrong: 0,
    missed: 2,
    corrections: [],
  });

  expect(formCount(avoided)).toBe("needed 2, never said");
  render(<FormPracticeList forms={[avoided]} />);
  expect(
    screen.getByText("said 0 times · needed 2 times where you said something else"),
  ).toBeInTheDocument();
});

test("an account with no forms counted is told what fills the list", () => {
  render(<FormPracticeList forms={[]} />);

  expect(screen.getByText(/A conversation of any length fills this in/)).toBeInTheDocument();
});

test("a form with more corrections than are listed says how many more", () => {
  render(<FormPracticeList forms={[makeFormPractice({ used: 10, right: 5, wrong: 5 })]} />);

  expect(screen.getByText(/and 4 more/)).toBeInTheDocument();
});
