/**
 * The per-sound panel, and the two states that are easy to render dishonestly.
 *
 * A sound with no baseline must not be drawn at zero — that places a speaker exactly on a
 * baseline that does not exist — and the whole panel must stay closed until there are
 * enough readings behind it, because the first few describe the microphone as much as the
 * mouth.
 */

import { render, screen } from "@testing-library/react";

import { PhonemeTrend } from "@/components/PhonemeTrend";

const OPEN = { shown: true, reason: null, have: 6, need: 5 };
const SHUT = {
  shown: false,
  reason:
    "2 scored readings so far. Per-sound trends start at 5, because the first few readings describe your microphone as much as your mouth.",
  have: 2,
  need: 5,
};

function phone(overrides = {}) {
  return {
    phone: "TH",
    mean_gop: -6.2,
    z: -1.8,
    baseline_mean: -3.1,
    baseline_readings: 4,
    samples: 30,
    ...overrides,
  };
}

test("too few readings closes the panel and says why", () => {
  render(<PhonemeTrend phones={[]} gate={SHUT} />);

  expect(screen.getByTestId("phone-gate")).toHaveTextContent("describe your microphone");
});

test("a sound below its own baseline shows the distance, signed", () => {
  render(<PhonemeTrend phones={[phone()]} gate={OPEN} />);

  expect(screen.getByTestId("z-TH")).toHaveTextContent("-1.8 sd");
  expect(screen.getByText("/TH/")).toBeInTheDocument();
  expect(screen.getByText("30 instances")).toBeInTheDocument();
});

test("a sound above its own baseline is shown as an improvement rather than an absence", () => {
  render(<PhonemeTrend phones={[phone({ phone: "S", z: 1.2 })]} gate={OPEN} />);
  expect(screen.getByTestId("z-S")).toHaveTextContent("+1.2 sd");
});

test("a sound with no baseline says so instead of being drawn at zero", () => {
  render(
    <PhonemeTrend
      phones={[phone({ z: null, baseline_mean: null, baseline_readings: 0 })]}
      gate={OPEN}
    />,
  );

  expect(screen.getByText("no baseline yet")).toBeInTheDocument();
  expect(screen.queryByTestId("z-TH")).not.toBeInTheDocument();
  expect(screen.getByText(/comparison against yourself/i)).toBeInTheDocument();
});

test("an open panel with nothing in it says that too", () => {
  render(<PhonemeTrend phones={[]} gate={OPEN} />);
  expect(screen.getByText(/no sound has turned up often enough/i)).toBeInTheDocument();
});
