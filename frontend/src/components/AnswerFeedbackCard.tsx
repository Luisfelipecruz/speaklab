/**
 * What a language model made of the answer, beside the counts and labelled as such.
 *
 * **Its shorter version is shown only if a check let it through.** The check looks for
 * content words the speaker never said, and a version that added too many is withheld —
 * with the words that caused it, so the refusal is visible instead of silent. Every other
 * way the model can fail is said in one plain sentence, and none of them touches the
 * counts above, which is also said.
 */

import { Bot } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { AnswerFeedback } from "@/lib/api";

const UNAVAILABLE: Record<Exclude<AnswerFeedback["status"], "ok" | "refused">, string> = {
  unavailable:
    "The language model did not answer this time, so there is no feedback. Everything counted above is unaffected.",
  unparseable:
    "The language model answered in a shape this page cannot read, so there is no feedback this time.",
  skipped: "Nothing was heard, so nothing was sent to the language model.",
};

export function AnswerFeedbackCard({ feedback }: { feedback: AnswerFeedback | null }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Bot className="size-4 text-muted-foreground" aria-hidden="true" />
          <h3>What a language model made of it</h3>
        </CardTitle>
        {feedback && <CardDescription>{feedback.caveat}</CardDescription>}
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        {!feedback ? (
          <p className="text-muted-foreground">No feedback was asked for.</p>
        ) : feedback.status === "ok" || feedback.status === "refused" ? (
          <>
            {feedback.lead && (
              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
                  Say this first
                </span>
                <p>{feedback.lead}</p>
              </div>
            )}
            {feedback.gaps.length > 0 && (
              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
                  No reason or example for
                </span>
                <ul className="list-disc pl-5">
                  {feedback.gaps.map((gap) => (
                    <li key={gap}>{gap}</li>
                  ))}
                </ul>
              </div>
            )}
            {feedback.rewrite ? (
              <div className="flex flex-col gap-1" data-testid="rewrite">
                <span className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
                  Your answer, shorter
                  {feedback.rewrite_sentences !== null &&
                    ` — ${feedback.rewrite_sentences} sentence${feedback.rewrite_sentences === 1 ? "" : "s"}`}
                </span>
                <blockquote className="border-l-2 border-muted pl-3 leading-relaxed">
                  {feedback.rewrite}
                </blockquote>
              </div>
            ) : (
              feedback.status === "refused" && (
                <p className="text-muted-foreground" data-testid="rewrite-withheld">
                  A shorter version was written and is not shown: it used words you never
                  said — {feedback.invented.map((word) => `“${word}”`).join(", ")}.
                </p>
              )
            )}
          </>
        ) : (
          <p className="text-muted-foreground">{UNAVAILABLE[feedback.status]}</p>
        )}
      </CardContent>
    </Card>
  );
}
