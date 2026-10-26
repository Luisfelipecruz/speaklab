/**
 * Writing on your own: how often you asked for English, and how you wrote it yourself.
 *
 * Drawn as a family is, with the same gates — a rate over fewer written words than speech
 * needs is a hole with its reason — and with how it is counted beside the lines. Counted
 * apart from speech: nothing here moves a spoken figure, and nothing spoken reaches it.
 */

import { MetricPanel } from "@/components/MetricPanel";
import { StatTile } from "@/components/StatTile";
import type { MetricFamily, Writing } from "@/lib/api";

/** The writing lines in a family's shape, for the panel and the overview's status line. */
export function asFamily(writing: Writing): MetricFamily {
  return {
    name: "writing",
    label: writing.label,
    description: writing.description,
    series: writing.series,
    caveat: writing.caveat,
  };
}

export function WritingPanel({ writing }: { writing: Writing }) {
  const { totals } = writing;
  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="asked for English" value={totals.captures} />
        <StatTile label="written yourself" value={totals.attempts} />
        <StatTile label="words written" value={totals.words} />
        <StatTile label="counted mistakes" value={totals.counted} />
      </div>
      <MetricPanel family={asFamily(writing)} />
    </div>
  );
}
