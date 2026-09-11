/**
 * The correction being practised, read before it is said.
 *
 * **Read first, because it may be wrong.** Every correction was proposed by grammar rules
 * or a language model and none was checked by a person, and saying a wrong correction
 * aloud practises the mistake. So the card leads with the sentence as it was said, what
 * was proposed instead and why, who proposed it — and the way out: skip it.
 *
 * When the sentence held other corrections they are applied too, and listed here, so
 * nothing in the sentence to be said is a change the learner has not been shown.
 */

import Link from "next/link";

import { RuleBadge } from "@/components/Corrections";
import { DrillSentence } from "@/components/DrillSentence";
import { humanise } from "@/components/ScenarioCard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Drill, DrillCorrection } from "@/lib/api";

function Badges({ correction }: { correction: DrillCorrection }) {
  return (
    <>
      {correction.subcategory && (
        <Badge variant="outline" className="text-xs">
          {humanise(correction.subcategory)}
        </Badge>
      )}
      {correction.detector === "rule" && <RuleBadge />}
      {!correction.counted && (
        <Badge variant="secondary" className="text-xs">
          {correction.asr_suspect ? "may be a mishearing" : "low confidence"}
        </Badge>
      )}
    </>
  );
}

export function DrillCorrectionCard({ drill }: { drill: Drill }) {
  const practised = drill.corrections.find((c) => c.id === drill.id) ?? drill.corrections[0];
  const others = drill.corrections.filter((c) => c.id !== practised.id);
  const when = new Date(drill.said_at).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          <span className="first-letter:uppercase">{practised.label}</span>
          <Badges correction={practised} />
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">You said</span>
          {drill.pieces.length > 0 ? (
            <DrillSentence drill={drill} as="said" />
          ) : (
            <p className="text-muted-foreground line-through">{practised.original}</p>
          )}
        </div>
        <p>
          <span aria-hidden="true">→ </span>
          <span className="sr-only">Proposed instead: </span>
          <span className="font-medium">{practised.correction || "(removed)"}</span>
          {practised.explanation && (
            <span className="text-muted-foreground"> — {practised.explanation}</span>
          )}
        </p>
        {others.length > 0 && (
          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">
              {others.length === 1
                ? "The sentence has one other correction, and it is in the sentence to say too:"
                : `The sentence has ${others.length} other corrections, and they are in the sentence to say too:`}
            </span>
            <ul className="flex flex-col gap-1">
              {others.map((other) => (
                <li key={other.id} className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-muted-foreground line-through">{other.original}</span>
                  <span aria-hidden="true">→</span>
                  <span>{other.correction || "(removed)"}</span>
                  <Badges correction={other} />
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="text-xs text-muted-foreground">
          From{" "}
          <Link
            href={`/sessions/${drill.session_id}`}
            className="underline underline-offset-4 hover:text-foreground"
          >
            {drill.scenario_title ?? "a conversation"}, {when}
          </Link>
          . Practise it only if you agree with it — if you think it is wrong, skip it.
        </p>
      </CardContent>
    </Card>
  );
}
