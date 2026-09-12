/**
 * One answer: how it was said, how it was built, and what a model made of it — in that
 * order, because the first two are counted and the third is an opinion.
 *
 * **Counts, not a grade.** Each figure is what the recording and the transcript hold.
 * Nothing is coloured as good or bad: speaking faster is nerves as often as fluency, and an
 * answer with more signposts is not a better answer — it needs the ones its idea needs.
 * The signposts are marked on the transcript so a count can be checked against the words.
 */

import { AnswerFeedbackCard } from "@/components/AnswerFeedbackCard";
import { MarkedTranscript } from "@/components/MarkedTranscript";
import { StatTile } from "@/components/StatTile";
import type { SpokenAnswer } from "@/lib/api";
import { KIND_HINT, KIND_LABEL, SIGNPOSTS, clock } from "@/lib/answers";

function rounded(value: number | null): string {
  return value === null ? "—" : String(Math.round(value));
}

export function AnswerResult({ answer }: { answer: SpokenAnswer }) {
  const { delivery, structure } = answer;
  return (
    <section className="flex flex-col gap-6" aria-labelledby={`answer-${answer.id}`}>
      <h2 id={`answer-${answer.id}`} className="text-lg font-semibold tracking-tight">
        {answer.again_of ? "Said again" : "Your answer"}
      </h2>

      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold">How you said it</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label={`words in ${clock(delivery.duration_ms)}`} value={delivery.words} />
          <StatTile label="words a minute" value={rounded(delivery.speech_rate_wpm)} />
          <StatTile
            label="of the time paused"
            value={delivery.pause_ratio === null ? "—" : `${Math.round(delivery.pause_ratio * 100)}%`}
          />
          <StatTile label={delivery.fillers === 1 ? "filler" : "fillers"} value={delivery.fillers} />
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold">How you built it</h3>
        <ul className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3 lg:grid-cols-5" aria-label="Signposts">
          {SIGNPOSTS.filter((kind) => structure.signposts[kind] !== undefined).map((kind) => (
            <li key={kind} className="flex flex-col rounded-lg border border-border px-3 py-2">
              <span className="text-xl font-semibold tabular-nums">{structure.signposts[kind]}</span>
              <span>{KIND_LABEL[kind]}</span>
              <span className="text-xs text-muted-foreground">{KIND_HINT[kind]}</span>
            </li>
          ))}
        </ul>
        <p className="text-sm text-muted-foreground tabular-nums">
          {structure.sentences !== null &&
            `${structure.sentences} sentence${structure.sentences === 1 ? "" : "s"}, ${structure.words_per_sentence ?? "—"} words each on average, the longest ${structure.longest_sentence ?? "—"}. `}
          {structure.repeats !== null &&
            `${structure.repeats} time${structure.repeats === 1 ? "" : "s"} a word or phrase was said twice.`}
        </p>
        <MarkedTranscript transcript={answer.transcript} found={structure.found} />
        <p className="text-xs leading-relaxed text-muted-foreground">{structure.caveat}</p>
      </div>

      <AnswerFeedbackCard feedback={answer.feedback} />
    </section>
  );
}
