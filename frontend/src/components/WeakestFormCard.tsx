/**
 * The one verb form to practise, and where — or why none is named yet.
 *
 * **Named only on enough evidence, and the card says what that means.** A form is named
 * once it has come up often enough to be a sample and been corrected often enough that
 * the corrections are unlikely all to be the detector's mistakes. Until then the card
 * says how far the nearest form is from that, in the API's words — an empty card would
 * read as "nothing to work on", which is a different claim and not one anything measured.
 */

import Link from "next/link";
import { Target } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Gate, WeakestForm } from "@/lib/api";

export function WeakestFormCard({ weakest, gate }: { weakest: WeakestForm | null; gate: Gate }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Target className="size-4 text-primary" aria-hidden="true" />
          {weakest ? (
            <span>
              Practise the <span className="text-primary">{weakest.label}</span>
            </span>
          ) : (
            "No form to practise named yet"
          )}
        </CardTitle>
        <CardDescription>{weakest ? weakest.reason : gate.reason}</CardDescription>
      </CardHeader>
      {weakest?.scenario_slug && (
        <CardContent>
          <Button asChild>
            <Link href={`/scenarios/${weakest.scenario_slug}`}>
              Practise it in {weakest.scenario_title}
            </Link>
          </Button>
        </CardContent>
      )}
      {!weakest && gate.need > 0 && (
        <CardContent>
          <p className="text-xs text-muted-foreground tabular-nums">
            {gate.have} of {gate.need} corrections on the nearest form
          </p>
        </CardContent>
      )}
    </Card>
  );
}
