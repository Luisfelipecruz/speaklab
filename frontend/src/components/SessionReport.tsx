/**
 * The end-of-session debrief. FR-9.
 *
 * **The three-way split is the design, and it is invariant I1 made visible.** The report
 * arrives from the API already separated by where each number came from — `measured`
 * counted from stored rows, `narrative` written by a language model, `pending` naming
 * the parts that need analysers which do not exist yet — and this component's one job is
 * to keep that separation on the screen instead of flattening it into a tidy summary.
 *
 * A flat report is one refactor away from a chart with a model's opinion on it. So the
 * generated prose is under a heading that says a model wrote it, and names the model;
 * the counted numbers are under a heading that says they were counted; and the missing
 * analyses are listed rather than omitted, because a report that silently leaves out
 * "errors" reads as a session that had none.
 *
 * When the narrative failed, the reason is printed. m6's `narrate_report` returns its
 * own failure rather than raising — ending a session must not depend on Ollama being up
 * — and "the model was unavailable" is a fact worth showing, not a section to hide.
 */

import { BarChart3, Bot, Hourglass } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { SessionReportShape } from "@/lib/api";

function duration(ms: number): string {
  const total = Math.round(ms / 1000);
  const minutes = Math.floor(total / 60);
  return minutes > 0 ? `${minutes}m ${total % 60}s` : `${total}s`;
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xl font-semibold tabular-nums">{value}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

export function SessionReport({ report }: { report: SessionReportShape }) {
  const { measured, narrative, pending } = report;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Session report</CardTitle>
        {report.goal && (
          <CardDescription>
            The goal was: <span className="text-foreground">{report.goal}</span>
          </CardDescription>
        )}
      </CardHeader>

      <CardContent className="flex flex-col gap-6">
        <section className="flex flex-col gap-3">
          <h3 className="flex items-center gap-2 text-sm font-medium">
            <BarChart3 className="size-4 text-primary" aria-hidden="true" />
            Counted from this session
          </h3>
          <p className="text-xs text-muted-foreground">
            Computed from the stored turns. The same conversation gives the same numbers
            every time.
          </p>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Figure label="your turns" value={String(measured.turns.user)} />
            <Figure label="words spoken" value={String(measured.words_spoken)} />
            <Figure label="length" value={duration(measured.duration_ms)} />
            <Figure
              label="median reply time"
              value={
                measured.median_turn_latency_ms === null
                  ? "—"
                  : `${(measured.median_turn_latency_ms / 1000).toFixed(1)}s`
              }
            />
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            {measured.mean_asr_confidence !== null && (
              <Badge variant="outline">
                mean recogniser confidence {measured.mean_asr_confidence.toFixed(2)}
              </Badge>
            )}
            {measured.min_turns !== null && (
              <Badge variant={measured.reached_min_turns ? "default" : "secondary"}>
                {measured.reached_min_turns
                  ? `reached the ${measured.min_turns}-turn minimum`
                  : `short of the ${measured.min_turns}-turn minimum`}
              </Badge>
            )}
          </div>
        </section>

        <Separator />

        <section className="flex flex-col gap-3">
          <h3 className="flex items-center gap-2 text-sm font-medium">
            <Bot className="size-4 text-primary" aria-hidden="true" />
            Written by the language model
          </h3>
          <p className="text-xs text-muted-foreground">
            Prose and a judgement about the goal, generated from the transcript
            {narrative?.status === "ok" ? ` by ${narrative.model}` : ""}. It is not a
            measurement and nothing here is plotted over time.
          </p>

          {narrative?.status === "ok" ? (
            <div className="flex flex-col gap-2 text-sm">
              <p className="leading-relaxed">{narrative.summary}</p>
              {narrative.note && (
                <p className="leading-relaxed text-muted-foreground">{narrative.note}</p>
              )}
              {narrative.goal_met !== null && (
                <Badge variant={narrative.goal_met ? "default" : "secondary"} className="w-fit">
                  {narrative.goal_met ? "the model judged the goal met" : "the model judged the goal not met"}
                </Badge>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {narrative === null
                ? "No narrative was produced for this session."
                : narrative.status === "skipped"
                  ? "There was nothing to summarise — this session has no transcribed turns."
                  : narrative.status === "unavailable"
                    ? "The language model was not available when this session ended, so there is no written summary. The counted figures above are unaffected."
                    : "The model did not answer in the format this report asks for, so nothing was salvaged from it."}
            </p>
          )}
        </section>

        <Separator />

        <section className="flex flex-col gap-3">
          <h3 className="flex items-center gap-2 text-sm font-medium">
            <Hourglass className="size-4 text-muted-foreground" aria-hidden="true" />
            Not measured yet
          </h3>
          <p className="text-xs text-muted-foreground">
            FR-9 asks for these and the analysers that produce them are not built. Listed
            rather than omitted: a report with no errors section reads like a session with
            no errors.
          </p>
          <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
            {Object.entries(pending).map(([name, note]) => (
              <li key={name} className="flex gap-2">
                <span className="font-medium text-foreground">{name.replace(/_/g, " ")}</span>
                <span>— {note}</span>
              </li>
            ))}
          </ul>
        </section>
      </CardContent>
    </Card>
  );
}
