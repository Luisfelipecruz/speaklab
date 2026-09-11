/**
 * The form to practise, or why none is named yet.
 *
 * Below the floor the card must say something, and what it says is the API's reason and
 * how near the nearest form is — never an empty card, which would read as "nothing to work
 * on".
 */

import { render, screen } from "@testing-library/react";

import { WeakestFormCard } from "@/components/WeakestFormCard";
import type { Gate, WeakestForm } from "@/lib/api";

const BELOW: Gate = {
  shown: false,
  reason: "The form with the most corrections so far is the past simple: 2 corrections, from the 11 times it was said or needed.",
  have: 2,
  need: 5,
};

const NAMED: WeakestForm = {
  form: "present_perfect",
  label: "present perfect",
  used: 1,
  right: 0,
  wrong: 1,
  missed: 5,
  reason: "Right 0 of 6 — said wrongly once and needed 5 times where you said something else.",
  scenario_slug: "doctors-appointment",
  scenario_title: "Doctor's appointment",
};

test("below the floor it names nothing and says how far the nearest form is", () => {
  render(<WeakestFormCard weakest={null} gate={BELOW} />);

  expect(screen.getByText("No form to practise named yet")).toBeInTheDocument();
  expect(screen.getByText(BELOW.reason as string)).toBeInTheDocument();
  expect(screen.getByText("2 of 5 corrections on the nearest form")).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

test("a named form comes with its counts and the scenario that asks for it", () => {
  render(<WeakestFormCard weakest={NAMED} gate={{ shown: true, reason: null, have: 6, need: 5 }} />);

  expect(screen.getByText("present perfect")).toBeInTheDocument();
  expect(screen.getByText(NAMED.reason)).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Practise it in Doctor's appointment" }),
  ).toHaveAttribute("href", "/scenarios/doctors-appointment");
});

test("a named form no scenario asks for offers nowhere to go", () => {
  render(
    <WeakestFormCard
      weakest={{ ...NAMED, scenario_slug: null, scenario_title: null }}
      gate={{ shown: true, reason: null, have: 6, need: 5 }}
    />,
  );

  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});
