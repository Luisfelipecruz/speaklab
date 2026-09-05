/**
 * The chart, and the two things it must never do.
 *
 * **It must not close a gap.** A period with too little speech in it is a hole, and the
 * line has to break there. Joining across it draws two distant sessions as continuous
 * practice, which is the most flattering lie a progress chart can tell — and it is the
 * default behaviour of every charting library, which is part of why there is not one here.
 *
 * **It must not claim a direction it was not given.** The API decides which metrics have a
 * defensibly better end; the component renders that decision and never infers one from the
 * numbers in front of it.
 */

import { render, screen } from "@testing-library/react";

import { TrendChart, format } from "@/components/TrendChart";
import { makeSeries } from "@/test/fixtures";

function polylines(): NodeListOf<Element> {
  return screen.getByTestId("trend-svg").querySelectorAll("polyline");
}

test("a suppressed series says what it is waiting for instead of drawing an empty box", () => {
  render(
    <TrendChart
      series={makeSeries({
        points: [{ start: "2026-08-31", value: null, samples: 12, withheld: "too thin" }],
        gate: {
          shown: false,
          reason: "No period yet has 50 words in it — the most any has is 12.",
          have: 12,
          need: 50,
        },
      })}
    />,
  );

  expect(screen.getByTestId("gate-reason")).toHaveTextContent("the most any has is 12");
  expect(screen.queryByTestId("trend-svg")).not.toBeInTheDocument();
});

test("measured periods are drawn as one line", () => {
  render(<TrendChart series={makeSeries()} />);
  expect(polylines()).toHaveLength(1);
});

test("a gap breaks the line rather than being joined across", () => {
  render(
    <TrendChart
      series={makeSeries({
        points: [
          { start: "2026-08-10", value: 8, samples: 200, withheld: null },
          { start: "2026-08-17", value: null, samples: 0, withheld: "nothing recorded" },
          { start: "2026-08-24", value: 3, samples: 300, withheld: null },
        ],
      })}
    />,
  );

  expect(polylines()).toHaveLength(2);
});

test("a missing period is still listed, so silence takes up the room it took up", () => {
  render(
    <TrendChart
      series={makeSeries({
        points: [
          { start: "2026-08-10", value: 8, samples: 200, withheld: null },
          { start: "2026-08-17", value: null, samples: 0, withheld: "nothing recorded" },
          { start: "2026-08-24", value: 3, samples: 300, withheld: null },
        ],
      })}
    />,
  );

  expect(screen.getByText("08/17")).toBeInTheDocument();
  expect(screen.getByTitle("nothing recorded")).toBeInTheDocument();
});

test("a direction is shown when the API sent one", () => {
  render(<TrendChart series={makeSeries()} />);
  expect(screen.getByTestId("direction")).toHaveTextContent("improving");
});

test("a metric with no better end is drawn and never judged", () => {
  // Speech rate. Faster is nerves as often as it is fluency, so the series arrives with
  // no direction for ever — and the component must not invent one from the slope.
  render(
    <TrendChart
      series={makeSeries({
        metric: "speech_rate_wpm",
        label: "speech rate",
        unit: "wpm",
        better: null,
        direction: null,
        change: null,
      })}
    />,
  );

  expect(screen.getByTestId("trend-svg")).toBeInTheDocument();
  expect(screen.queryByTestId("direction")).not.toBeInTheDocument();
});

test("the latest value is the one shown large", () => {
  render(<TrendChart series={makeSeries()} />);
  // Three points ending at 3, not the first one and not an average.
  expect(screen.getByText("3", { selector: "span.font-semibold" })).toBeInTheDocument();
});

test("a series that never changed is drawn rather than dividing by zero", () => {
  render(
    <TrendChart
      series={makeSeries({
        points: [
          { start: "2026-08-17", value: 5, samples: 200, withheld: null },
          { start: "2026-08-24", value: 5, samples: 200, withheld: null },
        ],
        direction: "flat",
        change: 0,
      })}
    />,
  );

  expect(polylines()).toHaveLength(1);
  expect(screen.getByTestId("direction")).toHaveTextContent("unchanged");
});

describe("formatting", () => {
  test("a ratio is shown as a percentage, because nobody reads 0.18 as time paused", () => {
    expect(format(0.18, "ratio")).toBe("18%");
  });

  test("precision follows magnitude rather than being fixed", () => {
    expect(format(2.567, "per 100 words")).toBe("2.57");
    expect(format(118.42, "wpm")).toBe("118");
  });
});
