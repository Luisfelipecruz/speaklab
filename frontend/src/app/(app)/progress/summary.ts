import { drawablePoints, type MetricFamily } from "@/lib/api";

/**
 * What a family has to show, in one line, without opening it.
 *
 * Counted from the same points the charts draw, so it can never disagree with them.
 */
export function familyStatus(family: MetricFamily): string {
  const shown = family.series.filter((series) => series.gate.shown);
  if (shown.length === 0) return "Nothing measured yet";

  const weeks = Math.max(...shown.map((series) => drawablePoints(series).length));
  if (weeks === 0) return "Nothing measured yet";
  if (weeks === 1) {
    return `${shown.length} measurement${shown.length === 1 ? "" : "s"}, one week. A trend starts at two.`;
  }

  const moving = shown.filter((series) => series.direction).length;
  const counted = `${shown.length} measurement${shown.length === 1 ? "" : "s"} across ${weeks} weeks`;
  return moving > 0
    ? `${counted}, ${moving} with a direction`
    : `${counted}, none of them judged`;
}
