/**
 * What to practise next, with the measurement that chose it printed underneath.
 *
 * **The reason is the feature.** Any product can put three suggestions on a page; what
 * makes these worth acting on is that each one says the number it came from — *"six
 * corrections in two hundred and seventy-two words"* — which a learner can go and check
 * against their own transcripts. A suggestion with no traceable reason is indistinguishable
 * from a guess, and this system does not guess.
 *
 * **How sure it is, said out loud.** `confidence` comes from the same sample counts the
 * charts are gated on, and the low state is not an apology — it is the difference between
 * a ranking that is probably right and one that is definitely right, and the reader is
 * entitled to know which they are looking at.
 *
 * Each entry links to the thing that would produce the practice: a scenario built to
 * elicit a form, a passage engineered around a sound. Advice with nowhere to act on it is
 * not advice.
 */

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Recommendation, Recommendations } from "@/lib/api";

export interface NextUpCardProps {
  recommendations: Recommendations;
}

const KIND_LABEL: Record<Recommendation["kind"], string> = {
  error_category: "corrections",
  weak_phone: "pronunciation",
  unused_form: "breadth",
  practise: "getting started",
};

const CONFIDENCE_LABEL: Record<Recommendations["confidence"], string> = {
  none: "nothing measured yet",
  low: "thin evidence",
  moderate: "moderate evidence",
  good: "well supported",
};

function destination(item: Recommendation): { href: string; label: string } | null {
  if (item.scenario_slug) {
    return { href: `/scenarios/${item.scenario_slug}`, label: "Practise this" };
  }
  if (item.passage_slug) {
    return { href: `/read/${item.passage_slug}`, label: "Read a passage" };
  }
  if (item.kind === "practise") {
    return { href: "/scenarios", label: "Choose a scenario" };
  }
  return null;
}

export function NextUpCard({ recommendations }: NextUpCardProps) {
  const { items, confidence, detail } = recommendations;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">What to practise next</CardTitle>
        <CardDescription>
          Ranked by a weighted score over your stored corrections, the forms you have not
          reached for, and the sounds that score worst. No model is involved in the choice.
        </CardDescription>
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            variant={confidence === "good" ? "default" : "secondary"}
            data-testid="confidence"
          >
            {CONFIDENCE_LABEL[confidence]}
          </Badge>
          {detail && <span className="text-xs text-muted-foreground">{detail}</span>}
        </div>

        <ul className="flex flex-col gap-4">
          {items.map((item) => {
            const target = destination(item);
            return (
              <li
                key={`${item.kind}-${item.title}`}
                className="flex flex-col gap-1.5 border-l-2 border-primary/40 pl-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{item.title}</span>
                  <Badge variant="outline" className="text-[10px]">
                    {KIND_LABEL[item.kind]}
                  </Badge>
                </div>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {item.reason}
                </p>
                {target && (
                  <Button asChild variant="link" size="sm" className="h-auto w-fit p-0">
                    <Link href={target.href}>{target.label}</Link>
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
