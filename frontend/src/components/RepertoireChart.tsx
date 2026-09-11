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
 * **Each verb form carries how often it was right**, counted over the times it was used and
 * the times it was needed and something else was said. The second half is why a form the
 * learner never said can still be listed: "needed 3, never said" is the avoidance this
 * panel exists to show. It is a count and never a percentage, although the API sends one
 * above its floor: the floor is about the size of the sample, and the corrections behind
 * the count — the language model's, for every tense — are the larger error. The API's
 * caveat is rendered here too, because this panel is read away from the error-rate chart
 * that carries one.
 */

import Link from "next/link";
import { Info, TriangleAlert } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { FormAccuracy, Repertoire } from "@/lib/api";

export interface RepertoireChartProps {
  repertoire: Repertoire;
}

/** `going_to_future` reads as "going to future" to somebody who is not a linguist. */
function readable(form: string): string {
  return form.replace(/_/g, " ");
}

/** "right 9 of 13", or "needed 2, never said". */
function accuracyText(tally: FormAccuracy): string {
  if (tally.used === 0) {
    return `needed ${tally.missed}, never said`;
  }
  return `right ${tally.right} of ${tally.used + tally.missed}`;
}

function times(count: number): string {
  return count === 1 ? "1 time" : `${count} times`;
}

/** The same figures in words, for the tooltip. */
function accuracyDetail(tally: FormAccuracy): string {
  const said = `said ${times(tally.used)}, ${tally.wrong} of them corrected`;
  return tally.missed > 0
    ? `${said}; needed ${times(tally.missed)} more where another form was said`
    : said;
}

export function RepertoireChart({ repertoire }: RepertoireChartProps) {
  const counts: Record<string, number> = { ...repertoire.forms };
  for (const [form, tally] of Object.entries(repertoire.accuracy)) {
    if (!(form in counts) && tally.missed > 0) {
      counts[form] = 0;
    }
  }
  const forms = Object.entries(counts).sort(
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
          Beside each tense and modal: how often it was right, out of the times you used it
          and the times it was needed and you said something else. The{" "}
          <Link href="/grammar" className="underline underline-offset-4">
            grammar page
          </Link>{" "}
          has the corrections behind each count.
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

        {repertoire.caveat && (
          <p
            className="flex max-w-3xl gap-2 rounded-lg border border-chart-2/40 bg-chart-2/10 p-3 text-sm leading-relaxed text-foreground"
            data-testid="form-accuracy-caveat"
          >
            <Info className="mt-1 size-4 shrink-0 text-chart-2" aria-hidden="true" />
            <span>{repertoire.caveat}</span>
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
              {forms.map(([form, count]) => {
                const tally = repertoire.accuracy[form];
                return (
                  <li key={form} className="flex flex-col gap-0.5 text-sm">
                    <span className="flex items-center gap-3">
                      <span className="w-44 shrink-0 truncate" title={readable(form)}>
                        {readable(form)}
                      </span>
                      <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-muted">
                        {count > 0 && (
                          <span
                            className="block h-full rounded-full bg-chart-1"
                            style={{ width: `${Math.max(4, (count / most) * 100)}%` }}
                            aria-hidden="true"
                          />
                        )}
                      </span>
                      <span className="w-8 text-right font-medium tabular-nums">{count}</span>
                    </span>
                    {tally && (
                      <span
                        className="pl-47 text-xs text-muted-foreground tabular-nums"
                        title={accuracyDetail(tally)}
                        data-testid={`form-accuracy-${form}`}
                      >
                        {accuracyText(tally)}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
