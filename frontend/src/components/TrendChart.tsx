/**
 * One metric over time, as a line — or as the reason there is no line yet.
 *
 * **Drawn by hand in SVG, and that is a decision.** A charting library is three hundred
 * kilobytes and an API to learn, and what this page needs is a polyline through at most a
 * few dozen points. More to the point, every library draws a continuous line through
 * whatever it is given, and the whole design here rests on the opposite: a period below
 * the sample floor is a **hole**, and it has to look like one. Making a library render
 * absence correctly is more work than not using one.
 *
 * **A gap is drawn as a gap.** Points with no value break the line rather than being
 * skipped over, so a fortnight of silence occupies the width it actually occupied.
 * Joining across it would draw two distant sessions as continuous practice, which is the
 * most flattering lie a progress chart can tell.
 *
 * **One measured period is a reading, not a trend, and it is drawn as one.** A single dot
 * in the middle of an empty box is the shape of a broken chart, and for the first months
 * of an account that is every series on the page — eleven boxes, eleven dots, nothing
 * legible. The same number set large, with the week it came from and what a second point
 * would take, says more and takes less room.
 *
 * **The verdict is separate from the numbers.** A direction is rendered only when the API
 * sent one, and it only sends one for a metric with a defensibly better end and enough
 * points to compare. Speech rate arrives with no direction for ever, on purpose.
 *
 * The line is decoration for people who can see it; the values are also rendered as text
 * for those who cannot, which is the same list the tests read.
 */

import { Badge } from "@/components/ui/badge";
import { drawablePoints, type TrendSeries } from "@/lib/api";
import { cn } from "@/lib/utils";

const WIDTH = 320;
const HEIGHT = 72;
const PADDING = 6;

export interface TrendChartProps {
  series: TrendSeries;
  /**
   * What one point is. The progress page draws a week per point; the answers page draws
   * an answer per point, and two answers can share a date.
   */
  per?: "week" | "answer";
}

/** Enough precision to see a change, never more than the measurement supports. */
export function format(value: number, unit: string | null): string {
  const decimals = Math.abs(value) < 10 ? 2 : Math.abs(value) < 100 ? 1 : 0;
  const rounded = Number(value.toFixed(decimals));
  return unit === "ratio" ? `${Math.round(value * 100)}%` : String(rounded);
}

function when(iso: string): string {
  // Fixed formatting rather than the viewer's locale: this is rendered on the server and
  // again in the browser, and a locale-dependent date is the classic hydration mismatch.
  return iso.slice(5).replace("-", "/");
}

const DIRECTION_LABEL: Record<string, string> = {
  improving: "improving",
  slipping: "slipping",
  flat: "unchanged",
};

/**
 * The label, the unit, the latest figure and any verdict — the same row whether what
 * follows it is a line or a single number.
 */
function Caption({ series, latest }: { series: TrendSeries; latest: number }) {
  return (
    <figcaption className="flex flex-wrap items-baseline gap-2">
      <span className="text-sm font-semibold">{series.label}</span>
      {series.unit && <span className="text-xs text-muted-foreground">{series.unit}</span>}
      <span className="ml-auto text-sm font-semibold tabular-nums">
        {format(latest, series.unit)}
      </span>
      {series.direction && (
        <Badge
          variant={series.direction === "slipping" ? "secondary" : "default"}
          className="text-xs"
          data-testid="direction"
        >
          {DIRECTION_LABEL[series.direction]}
        </Badge>
      )}
    </figcaption>
  );
}

export function TrendChart({ series, per = "week" }: TrendChartProps) {
  const drawable = drawablePoints(series);

  // The three states share one box, so a family's series line up as a grid of equal
  // panels whether each one is a line, a single reading or a reason. A gated series is
  // the only one drawn with a dashed edge: it is a placeholder, and should look like one.
  if (!series.gate.shown) {
    return (
      <div className="flex flex-col gap-1 rounded-lg border border-dashed border-border bg-muted/40 p-4">
        <span className="text-sm font-semibold">{series.label}</span>
        <p className="text-sm text-muted-foreground" data-testid="gate-reason">
          {series.gate.reason}
        </p>
      </div>
    );
  }

  if (drawable.length === 1) {
    const only = drawable[0];
    return (
      <figure className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4">
        <Caption series={series} latest={only.value as number} />
        <p
          className="text-3xl font-bold tracking-tight tabular-nums"
          data-testid="single-reading"
        >
          {format(only.value as number, series.unit)}
          {series.unit && series.unit !== "ratio" && (
            <span className="ml-1.5 text-sm font-normal text-muted-foreground">
              {series.unit}
            </span>
          )}
        </p>
        <p className="text-xs text-muted-foreground">
          {per === "week"
            ? `Measured once, in the week of ${when(only.start)}. A line needs a second week with practice in it.`
            : `Measured on one answer, on ${when(only.start)}. A line needs a second answer long enough to count.`}
        </p>
      </figure>
    );
  }

  const values = drawable.map((point) => point.value as number);
  const lowest = Math.min(...values);
  const highest = Math.max(...values);
  // A flat series would divide by zero and, worse, would be drawn as a line at the top of
  // the box — which reads as a maximum rather than as "this did not change".
  const spread = highest - lowest || 1;

  const x = (index: number) =>
    series.points.length <= 1
      ? WIDTH / 2
      : PADDING + (index * (WIDTH - PADDING * 2)) / (series.points.length - 1);
  const y = (value: number) =>
    HEIGHT - PADDING - ((value - lowest) / spread) * (HEIGHT - PADDING * 2);

  // Split into runs of consecutive measured points. Each run is its own polyline, which
  // is what leaves the holes empty instead of bridging them.
  const runs: { index: number; value: number }[][] = [];
  let run: { index: number; value: number }[] = [];
  series.points.forEach((point, index) => {
    if (point.value === null) {
      if (run.length) runs.push(run);
      run = [];
      return;
    }
    run.push({ index, value: point.value });
  });
  if (run.length) runs.push(run);

  const floor = HEIGHT - PADDING;

  return (
    <figure className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4">
      <Caption series={series} latest={values[values.length - 1]} />

      {/* The accent colour, at full strength for the line and faintly under it. A
          hairline in grey was the chart the person could not see; the area is what makes
          the line read as a quantity rather than as a scratch on the card. Each run gets
          its own area, so a hole in the data is a hole in the fill too. */}
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-24 w-full text-chart-1"
        preserveAspectRatio="none"
        role="img"
        aria-label={`${series.label} over ${drawable.length} ${per === "week" ? "periods" : "answers"}`}
        data-testid="trend-svg"
      >
        {runs.map((points, position) => {
          const path = points.map((point) => `${x(point.index)},${y(point.value)}`);
          const first = x(points[0].index);
          const last = x(points[points.length - 1].index);
          return (
            <g key={position}>
              {points.length > 1 && (
                <polygon
                  fill="currentColor"
                  fillOpacity={0.12}
                  points={[...path, `${last},${floor}`, `${first},${floor}`].join(" ")}
                />
              )}
              <polyline
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
                points={path.join(" ")}
              />
            </g>
          );
        })}
        {drawable.map((point) => {
          const index = series.points.indexOf(point);
          return (
            <circle
              key={index}
              cx={x(index)}
              cy={y(point.value as number)}
              r={3}
              fill="currentColor"
              stroke="var(--card)"
              strokeWidth={1.5}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </svg>

      {/* The same numbers as text. It is what a screen reader gets, and it is what makes
          the component testable without asserting against SVG path arithmetic. */}
      <ul className="flex flex-wrap justify-between gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {/* Keyed by position: two answers on one day share a date. */}
        {series.points.map((point, index) => (
          <li
            key={index}
            className={cn("tabular-nums", point.value === null && "italic")}
            title={point.withheld ?? undefined}
          >
            {when(point.start)}{" "}
            <span className={cn(point.value !== null && "text-foreground")}>
              {point.value === null ? "—" : format(point.value, series.unit)}
            </span>
          </li>
        ))}
      </ul>
    </figure>
  );
}
