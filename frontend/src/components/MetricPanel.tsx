/**
 * One family of measurements — how you speak, what you get wrong, how much you reach for,
 * how you sound — with everything needed to read it honestly attached to it.
 *
 * **The caveat is part of the family, not a footnote.** Only one of the four carries one:
 * the error rate is an exact count of stored rows, but the categories those rows are filed
 * under came from a language model whose labelling measured 0.50 precision on this
 * project's own hand-checked set. That belongs next to the chart it qualifies, where
 * somebody deciding what to practise will actually read it — not in a document they will
 * not open.
 *
 * A family whose every series is suppressed is still rendered, with its heading and its
 * reasons. Hiding it would leave the page looking like a product with three metric
 * families, and a user with nothing to see would have no way to find out what would make
 * something appear.
 */

import { Info } from "lucide-react";

import { TrendChart } from "@/components/TrendChart";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { MetricFamily } from "@/lib/api";

export interface MetricPanelProps {
  family: MetricFamily;
}

export function MetricPanel({ family }: MetricPanelProps) {
  const drawn = family.series.filter((series) => series.gate.shown);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{family.label}</CardTitle>
        <CardDescription>{family.description}</CardDescription>
      </CardHeader>

      <CardContent className="flex flex-col gap-5">
        {family.caveat && (
          <p
            className="flex gap-2 rounded-md border border-border bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground"
            data-testid="caveat"
          >
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <span>{family.caveat}</span>
          </p>
        )}

        {drawn.length === 0 && (
          <p className="text-xs text-muted-foreground">
            Nothing here has enough behind it to draw yet. Each line below says what it is
            waiting for.
          </p>
        )}

        <div className="grid gap-5 sm:grid-cols-2">
          {family.series.map((series) => (
            <TrendChart key={series.metric} series={series} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
