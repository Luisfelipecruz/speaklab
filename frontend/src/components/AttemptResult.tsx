/**
 * One attempt at the English, checked: the mistakes marked in the person's own words, how
 * many count, the forms they used, the closer version compared word by word, and when the
 * capture comes back.
 *
 * The schedule is said with its rule, so the box is something the person can predict
 * rather than a number that moved: no counted mistake moves it up a box, any counted
 * mistake sends it back to the first.
 */

import { CaptureFixes } from "@/components/CaptureFixes";
import { WordDiff } from "@/components/WordDiff";
import { Badge } from "@/components/ui/badge";
import type { CaptureAttempt } from "@/lib/api";
import { comesBack, VERSION_LABEL } from "@/lib/notebook";

const INTERVALS = [1, 3, 7, 14, 30];

export function AttemptResult({ attempt, zone }: { attempt: CaptureAttempt; zone?: string }) {
  const forms = Object.entries(attempt.forms).sort(([, a], [, b]) => b - a);
  const back = comesBack(attempt.due_at, zone);
  return (
    <section className="flex flex-col gap-6" aria-live="polite" aria-label="Your English, checked">
      <div className="flex flex-col gap-3">
        <h2 className="text-base font-semibold">Your English, checked</h2>
        <CaptureFixes text={attempt.text} fixes={attempt.errors} />
        <p className="text-sm text-muted-foreground" data-testid="attempt-count">
          {attempt.counted === 0
            ? `No counted mistake in ${attempt.word_count} words.`
            : `${attempt.counted} counted mistake${attempt.counted === 1 ? "" : "s"} in ${attempt.word_count} words` +
              (attempt.per_100_words !== null ? `: ${attempt.per_100_words} per 100 words.` : ".")}
        </p>
        {attempt.detail && <p className="text-sm text-muted-foreground">{attempt.detail}</p>}
      </div>

      {forms.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
            Forms you used
          </h3>
          <ul className="flex flex-wrap gap-1.5" aria-label="Forms you used">
            {forms.map(([form, count]) => (
              <li key={form}>
                <Badge variant="outline" className="text-xs">
                  {form.replaceAll("_", " ")}
                  {count > 1 ? ` ×${count}` : ""}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}

      {attempt.compared_with && attempt.compared_text && (
        <div className="flex flex-col gap-2">
          <h3 className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
            Beside the closer version · {VERSION_LABEL[attempt.compared_with]}
          </h3>
          <WordDiff
            label={`Your English beside ${VERSION_LABEL[attempt.compared_with]}`}
            steps={attempt.words.map((word) => ({ expected: word.expected, theirs: word.written }))}
          />
        </div>
      )}

      <p className="rounded-lg border border-border bg-muted/40 p-3 text-sm" data-testid="comes-back">
        {attempt.counted > 0
          ? "A counted mistake sends it back to box 1"
          : attempt.box > attempt.box_before
            ? `Up a box, to box ${attempt.box}`
            : `Still in the last box, box ${attempt.box}`}
        , so it comes back <strong>{back}</strong>. With no counted mistake it moves up a box
        each time —{" "}
        {INTERVALS.join(", ")} days.
      </p>
    </section>
  );
}
