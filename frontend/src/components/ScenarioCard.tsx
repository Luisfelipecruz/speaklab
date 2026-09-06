/**
 * One scenario in the catalogue.
 *
 * A server component — it has no state and no handlers, so shipping it to the browser
 * would be bundle for nothing. The whole card is a link, because a card with a "Start"
 * button in the corner makes the other 95 % of the target dead space.
 *
 * The declared target forms are shown, and that is a product decision rather than a
 * detail dump: a scenario declares the grammar it is designed to elicit, and the eval
 * harness later checks whether it actually elicited it. Showing the learner what a
 * scenario is *for* is the difference between choosing one and picking one at random.
 * `persona_prompt` is the opposite case and never leaves the server.
 */

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ScenarioSummary } from "@/lib/api";

/** `present_perfect` reads badly on a card; `present perfect` does not. */
export function humanise(token: string): string {
  return token.replace(/[_-]+/g, " ");
}

export function ScenarioCard({ scenario }: { scenario: ScenarioSummary }) {
  return (
    <Card className="relative transition-[border-color,box-shadow] hover:border-primary/50 hover:shadow-md">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="text-lg">
            <Link
              href={`/scenarios/${scenario.slug}`}
              // The pseudo-element makes the whole card the hit target while the anchor
              // itself stays a normal, focusable link with a readable accessible name.
              className="after:absolute after:inset-0 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {scenario.title}
            </Link>
          </CardTitle>
          <Badge variant="secondary">{scenario.cefr_band}</Badge>
        </div>
        <CardDescription>{scenario.description}</CardDescription>
      </CardHeader>

      <CardContent className="flex flex-wrap gap-1.5">
        <Badge variant="outline">{humanise(scenario.category)}</Badge>
        {scenario.target_grammar.slice(0, 3).map((form) => (
          <Badge key={form} variant="outline" className="font-normal text-muted-foreground">
            {humanise(form)}
          </Badge>
        ))}
      </CardContent>
    </Card>
  );
}
