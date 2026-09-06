/**
 * Which grammatical forms were actually produced, and whether the range of them is
 * narrowing.
 *
 * **This panel exists to stop a falling error rate being read as improvement.** A learner
 * who retreats to the present simple makes fewer mistakes, and an accuracy chart on its
 * own calls that progress. Breadth is the other half of the picture and it is deliberately
 * rendered next to it: the two numbers only mean something read together.
 *
 * So one specific combination gets a warning rather than a chart — fewer forms *and* fewer
 * errors than last period. Every other combination is left to the numbers, including a
 * narrowing repertoire with a rising error rate, which is just a bad week and already
 * looks like one.
 *
 * **There is no accuracy per form here, and that is a limit worth naming.** Corrections are
 * filed under a taxonomy category and forms are counted by a parser; nothing links one to
 * the other, so a per-form accuracy bar would be an invented join with decimal places.
 */

import { TriangleAlert } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Repertoire } from "@/lib/api";

export interface RepertoireChartProps {
  repertoire: Repertoire;
}

/** `going_to_future` reads as "going to future" to somebody who is not a linguist. */
function readable(form: string): string {
  return form.replace(/_/g, " ");
}

export function RepertoireChart({ repertoire }: RepertoireChartProps) {
  const forms = Object.entries(repertoire.forms).sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
  );
  const most = forms.length > 0 ? forms[0][1] : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">The forms you reached for</CardTitle>
        <CardDescription>
          Counted from a parse of what you said, not judged. Breadth is here because a
          narrower range of forms lowers an error rate without anybody getting better.
        </CardDescription>
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        {repertoire.warning && (
          <p
            className="flex max-w-3xl gap-2 rounded-lg border border-chart-2/40 bg-chart-2/10 p-3 text-sm leading-relaxed"
            data-testid="repertoire-warning"
          >
            <TriangleAlert className="mt-1 size-4 shrink-0 text-chart-2" aria-hidden="true" />
            <span>{repertoire.warning}</span>
          </p>
        )}

        {forms.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing counted yet. A conversation of any length fills this in.
          </p>
        ) : (
          <>
            <p className="text-sm">
              <span className="font-semibold tabular-nums">
                {repertoire.distinct_forms}
              </span>{" "}
              different forms
              {repertoire.previous_distinct_forms !== null && (
                <span className="text-muted-foreground">
                  {" "}
                  — {repertoire.previous_distinct_forms} the period before
                </span>
              )}
            </p>

            {/* Each bar sits on a full-width track, so the longest bar is visibly the
                whole and the others are visibly fractions of it. A bar on its own has
                nothing to be a fraction of. */}
            <ul className="flex flex-col gap-2">
              {forms.map(([form, count]) => (
                <li key={form} className="flex items-center gap-3 text-sm">
                  <span className="w-44 shrink-0 truncate" title={readable(form)}>
                    {readable(form)}
                  </span>
                  <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <span
                      className="block h-full rounded-full bg-chart-1"
                      style={{ width: `${Math.max(4, (count / most) * 100)}%` }}
                      aria-hidden="true"
                    />
                  </span>
                  <span className="w-8 text-right font-medium tabular-nums">{count}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
