/**
 * One kind of correction, and the learner's own sentences it was proposed on.
 *
 * **The sentence is the point.** "Three verb-tense corrections" tells a learner nothing
 * they can act on; the sentence they said, with the words marked and what was proposed
 * instead, is something they can read, practise — and disagree with. Every correction here
 * was proposed by rules or a model and none was checked by a person, so the page's job is
 * to put the evidence in front of the reader rather than a verdict.
 *
 * The mark is the transcript's own words, drawn as they are on the transcript: amber and
 * solid when the correction counts, grey and dotted when it sits on words the recogniser
 * was unsure of or the model hedged. A correction whose words could not be placed is shown
 * on its own, without a sentence around it, rather than marked on the wrong words.
 *
 * A correction placed in its sentence can be said again: the link opens the drill, which
 * starts by showing the correction so that one the learner disagrees with can be skipped.
 * And a kind of correction that a scenario is written to draw out links to it, so more of
 * the same can be practised in a conversation.
 */

import Link from "next/link";
import { Mic } from "lucide-react";

import { RuleBadge } from "@/components/Corrections";
import { humanise } from "@/components/ScenarioCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { CategoryCorrections, CorrectionExample } from "@/lib/api";
import { cn } from "@/lib/utils";

function Sentence({ example }: { example: CorrectionExample }) {
  if (example.quote === null) {
    return <p className="text-sm text-muted-foreground line-through">{example.original}</p>;
  }
  return (
    <p className="text-sm leading-relaxed">
      <span>{example.before}</span>
      <mark
        className={cn(
          "rounded-sm px-0.5 text-inherit underline decoration-2 underline-offset-2",
          example.counted
            ? "bg-chart-2/20 decoration-chart-2"
            : "bg-muted decoration-muted-foreground decoration-dotted",
        )}
      >
        {example.quote}
      </mark>
      <span>{example.after}</span>
    </p>
  );
}

function Example({ example }: { example: CorrectionExample }) {
  const when = new Date(example.said_at).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
  return (
    <li className="flex flex-col gap-1.5 border-l-2 border-muted pl-3" data-testid="correction">
      <Sentence example={example} />
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <span aria-hidden="true">→</span>
        <span className="sr-only">Proposed instead:</span>
        <span className="font-medium">{example.correction}</span>
        {example.quote !== null && (
          <Button asChild variant="outline" size="sm" className="ml-auto h-7 gap-1.5 px-2.5 text-xs">
            <Link href={`/grammar/drill/${example.id}`}>
              <Mic aria-hidden="true" />
              Say it again
            </Link>
          </Button>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {example.subcategory && (
          <Badge variant="outline" className="text-xs">
            {humanise(example.subcategory)}
          </Badge>
        )}
        {example.detector === "rule" && <RuleBadge />}
        {!example.counted && (
          <Badge variant="secondary" className="text-xs">
            {example.asr_suspect ? "may be a mishearing" : "low confidence"}
          </Badge>
        )}
        {example.explanation && <span>{example.explanation}</span>}
        <Link
          href={`/sessions/${example.session_id}`}
          className="underline underline-offset-4 hover:text-foreground"
        >
          {example.scenario_title ?? "conversation"}, {when}
        </Link>
      </div>
    </li>
  );
}

export function GrammarCategory({ category }: { category: CategoryCorrections }) {
  const total = category.counted + category.not_counted;
  const unlisted = total - category.examples.length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-base">
          <span className="first-letter:uppercase">{category.label}</span>
          <span className="text-sm font-normal text-muted-foreground tabular-nums">
            {category.counted} counted
            {category.per_100_words !== null && ` · ${category.per_100_words} per 100 words`}
            {category.not_counted > 0 && ` · ${category.not_counted} not counted`}
          </span>
        </CardTitle>
        {category.description && (
          <CardDescription className="first-letter:uppercase">
            {category.description}
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <ul className="flex flex-col gap-4" aria-label={`${category.label} corrections`}>
          {category.examples.map((example) => (
            <Example key={example.id} example={example} />
          ))}
        </ul>
        {unlisted > 0 && (
          <p className="text-xs text-muted-foreground">
            The newest {category.examples.length} of {total}. The rest are marked on the
            conversations they came from.
          </p>
        )}
        {category.scenario_slug && (
          <p className="text-sm">
            <Link
              href={`/scenarios/${category.scenario_slug}`}
              className="underline underline-offset-4 hover:text-primary"
            >
              Practise these in {category.scenario_title}
              <span className="sr-only"> — {category.label} corrections</span>
            </Link>
          </p>
        )}
      </CardContent>
    </Card>
  );
}
