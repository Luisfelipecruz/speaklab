/**
 * The end-of-session debrief.
 *
 * **The split by provenance is the design.** The report arrives from the API already
 * separated by where each number came from — `measured` and the fluency and form counts
 * inside `analysis` computed from stored rows, the corrections proposed by a language
 * model and then checked, `narrative` written by one outright, `pending` naming what
 * still has no analyser — and this component's one job is to keep that separation on the
 * screen instead of flattening it into a tidy summary.
 *
 * A flat report is one refactor away from a chart with a model's opinion on it. So the
 * generated prose is under a heading that says a model wrote it and names it; the counted
 * numbers are under a heading that says they were counted; the corrections say which
 * layer found them; and what is missing is listed rather than omitted, because a report
 * that silently leaves out "errors" reads as a session that had none.
 *
 * **Two kinds of correction, rendered differently on purpose.** An error sitting on words
 * the recogniser was unsure of is shown and marked, and does not reach any rate. Hiding
 * it would leave the transcript with a hole in it; counting it would let a mishearing
 * move a number about the speaker. The badge is the whole difference and it is the reason
 * a learner can trust the rest.
 *
 * When the narrative failed, the reason is printed. The API returns that failure rather
 * than raising — ending a session must not depend on Ollama being up — and "the model was
 * unavailable" is a fact worth showing, not a section to hide.
 */

import { AlertTriangle, BarChart3, Bot, Gauge, Hourglass, SpellCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { LanguageErrorItem, SessionAnalysis, SessionReportShape } from "@/lib/api";

function duration(ms: number): string {
  const total = Math.round(ms / 1000);
  const minutes = Math.floor(total / 60);
  return minutes > 0 ? `${minutes}m ${total % 60}s` : `${total}s`;
}

/** `going_to_future` reads as "going to future" to somebody who is not a linguist. */
function readable(feature: string): string {
  return feature.replace(/_/g, " ");
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
  const analysis = report.analysis ?? null;

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

        {analysis && (
          <>
            <Separator />
            <AnalysisSections analysis={analysis} />
          </>
        )}

        <Separator />

        <section className="flex flex-col gap-3">
          <h3 className="flex items-center gap-2 text-sm font-medium">
            <Hourglass className="size-4 text-muted-foreground" aria-hidden="true" />
            Not measured yet
          </h3>
          <p className="text-xs text-muted-foreground">
            Nothing has produced these for this session. Listed rather than omitted: a
            report with no errors section reads like a session with no errors.
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


/**
 * Fluency, forms and corrections — everything the analysers wrote for this session.
 *
 * Three sections rather than one, in this order, because it is the order the claims get
 * weaker in: the fluency figures are arithmetic over word timings, the forms are a
 * dependency parse, and the corrections are a model's proposals that survived a closed
 * vocabulary and a check against the transcript.
 */
function AnalysisSections({ analysis }: { analysis: SessionAnalysis }) {
  const { fluency, target_forms: targets, errors } = analysis;

  return (
    <>
      <section className="flex flex-col gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          <Gauge className="size-4 text-primary" aria-hidden="true" />
          How you spoke
        </h3>
        <p className="text-xs text-muted-foreground">
          Arithmetic over the word timings. Speech rate spends the pauses; articulation
          rate takes them out, so getting faster by pausing less does not look like
          getting faster at speaking.
        </p>

        {fluency ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Figure
              label="speech rate (wpm)"
              value={fluency.speech_rate_wpm === null ? "—" : fluency.speech_rate_wpm.toFixed(0)}
            />
            <Figure
              label="articulation (wpm)"
              value={
                fluency.articulation_rate_wpm === null
                  ? "—"
                  : fluency.articulation_rate_wpm.toFixed(0)
              }
            />
            <Figure
              label="time paused"
              value={fluency.pause_ratio === null ? "—" : `${Math.round(fluency.pause_ratio * 100)}%`}
            />
            <Figure
              label="words per run"
              value={fluency.mean_length_run === null ? "—" : fluency.mean_length_run.toFixed(1)}
            />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            You did not speak in this session, so there is nothing to measure.
          </p>
        )}
      </section>

      <Separator />

      <section className="flex flex-col gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          <SpellCheck className="size-4 text-primary" aria-hidden="true" />
          Forms you used
        </h3>
        <p className="text-xs text-muted-foreground">
          Counted from a dependency parse, not judged. A scenario is built to draw out
          particular forms, and what it drew out is a set difference rather than an
          opinion.
        </p>

        {targets.declared.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {targets.elicited.map((form) => (
              <Badge key={form} variant="default">
                {readable(form)}
              </Badge>
            ))}
            {targets.not_elicited.map((form) => (
              <Badge key={form} variant="outline" className="text-muted-foreground">
                {readable(form)} — not used
              </Badge>
            ))}
          </div>
        )}

        {Object.keys(analysis.grammar_usage).length > 0 && (
          <p className="text-xs text-muted-foreground">
            Everything the parse found:{" "}
            {Object.entries(analysis.grammar_usage)
              .map(([feature, count]) => `${readable(feature)} ×${count}`)
              .join(", ")}
            .
          </p>
        )}
      </section>

      <Separator />

      <section className="flex flex-col gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          <AlertTriangle className="size-4 text-primary" aria-hidden="true" />
          Corrections
        </h3>
        <p className="text-xs text-muted-foreground">
          Proposed by a language model, then checked: the category comes from a fixed list
          and the words come from your transcript, so a correction cannot point at
          something you did not say.
        </p>

        {errors.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {analysis.complete
              ? "Nothing was flagged in what you said."
              : "Nothing yet — some turns have not been analysed."}
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {errors.items.map((item, index) => (
              <ErrorRow key={`${item.turn_id}-${item.span_start}-${index}`} item={item} />
            ))}
          </ul>
        )}

        <div className="flex flex-wrap items-center gap-2 text-xs">
          {errors.per_100_words !== null && (
            <Badge variant="outline">
              {errors.per_100_words} counted per 100 words
            </Badge>
          )}
          {errors.asr_suspect > 0 && (
            <Badge variant="secondary">
              {errors.asr_suspect} not counted — the recogniser was unsure
            </Badge>
          )}
        </div>

        {!analysis.complete && (
          <p className="text-xs text-muted-foreground">
            {analysis.turns_outstanding} of your turns have not been analysed yet. Open
            this session again to finish them.
          </p>
        )}
      </section>
    </>
  );
}

function ErrorRow({ item }: { item: LanguageErrorItem }) {
  return (
    <li className="flex flex-col gap-1 border-l-2 border-muted pl-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground line-through">{item.original}</span>
        <span aria-hidden="true">→</span>
        <span className="font-medium">{item.correction}</span>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Badge variant="outline" className="text-[10px]">
          {readable(item.category.toLowerCase())}
          {item.subcategory ? ` · ${readable(item.subcategory)}` : ""}
        </Badge>
        {!item.counted && (
          <Badge variant="secondary" className="text-[10px]">
            {item.asr_suspect ? "may be a mishearing" : "low confidence"}
          </Badge>
        )}
        {item.explanation && <span>{item.explanation}</span>}
      </div>
    </li>
  );
}
