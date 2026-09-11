/**
 * The verb forms a learner used, how often each was right, and the corrections behind
 * the count.
 *
 * **Counts, and the sentences under them — never a percentage.** "Right 9 of 13" is a
 * count a learner can check against the corrections listed beneath it; "69 %" is a grade,
 * and a grade built on corrections that are often wrong is one nobody should be given. A
 * form needed and never said is listed too, because avoiding a form is what this list is
 * for as much as getting one wrong.
 *
 * "Right" is what nobody corrected. A mistake the detector missed counts as right, and the
 * caveat above the page says so in as many words.
 */

import type { FormPractice } from "@/lib/api";

function times(count: number): string {
  return count === 1 ? "once" : `${count} times`;
}

/** "right 9 of 13", or "needed 2, never said". */
export function formCount(form: FormPractice): string {
  if (form.used === 0) return `needed ${form.missed}, never said`;
  return `right ${form.right} of ${form.used + form.missed}`;
}

/** Every correction behind the count is one said wrongly or one needed; a few are listed. */
function unlisted(form: FormPractice): number {
  return form.wrong + form.missed - form.corrections.length;
}

function breakdown(form: FormPractice): string {
  const parts = [`said ${times(form.used)}`];
  if (form.wrong > 0) parts.push(`corrected ${times(form.wrong)}`);
  if (form.missed > 0) parts.push(`needed ${times(form.missed)} where you said something else`);
  return parts.join(" · ");
}

export function FormPracticeList({ forms }: { forms: FormPractice[] }) {
  if (forms.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No tense or modal counted yet. A conversation of any length fills this in.
      </p>
    );
  }

  return (
    <ul className="flex flex-col divide-y divide-border" aria-label="Verb forms">
      {forms.map((form) => (
        <li
          key={form.form}
          className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0"
          data-testid={`form-${form.form}`}
        >
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <span className="font-medium first-letter:uppercase">{form.label}</span>
            <span className="text-sm tabular-nums">{formCount(form)}</span>
          </div>
          <p className="text-xs text-muted-foreground">{breakdown(form)}</p>
          {form.corrections.length > 0 && (
            <ul className="flex flex-col gap-1 text-sm" aria-label={`Corrections to the ${form.label}`}>
              {form.corrections.map((correction) => (
                <li key={correction.id} className="flex flex-wrap items-center gap-x-2">
                  <span className="text-muted-foreground line-through">{correction.original}</span>
                  <span aria-hidden="true">→</span>
                  <span>{correction.correction}</span>
                </li>
              ))}
            </ul>
          )}
          {unlisted(form) > 0 && (
            <p className="text-xs text-muted-foreground">
              and {unlisted(form)} more
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
