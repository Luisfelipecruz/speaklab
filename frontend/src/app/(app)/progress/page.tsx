/**
 * Whether you are getting better, and what to practise next.
 *
 * **The empty state is the main state, and it is designed rather than defaulted.** A new
 * account has nothing here, and so does an account with a fortnight of occasional
 * practice — which is most of them, for months. So every suppressed chart says what it is
 * waiting for, and the page opens with how much practice it is standing on rather than
 * with a number. Blank axes with no explanation read as a broken feature; "three more
 * readings" reads as an instruction.
 *
 * Server-rendered with the cookie forwarded, like the rest of the signed-in pages: the
 * figures are on screen at first paint instead of a round trip after it. The two requests
 * are issued together — they are independent, and doing them in series would make the
 * slowest page in the product twice as slow for no reason.
 */

import Link from "next/link";

import { RefreshProgress } from "@/app/(app)/progress/RefreshProgress";
import { MetricPanel } from "@/components/MetricPanel";
import { Page, PageHeader } from "@/components/PageHeader";
import { NextUpCard } from "@/components/NextUpCard";
import { PhonemeTrend } from "@/components/PhonemeTrend";
import { RepertoireChart } from "@/components/RepertoireChart";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { Progress, Recommendations } from "@/lib/api";
import { serverRequestOrNull } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Progress — SpeakLab" };

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xl font-semibold tabular-nums">{value}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

export default async function ProgressPage() {
  const [progress, recommendations] = await Promise.all([
    serverRequestOrNull<Progress>("/progress"),
    serverRequestOrNull<Recommendations>("/progress/recommendations"),
  ]);

  if (!progress || !recommendations) {
    return (
      <Page width="prose">
        <Alert>
          <AlertDescription>
            <Link href="/login?next=/progress" className="underline">
              Sign in
            </Link>{" "}
            to see how your practice is going.
          </AlertDescription>
        </Alert>
      </Page>
    );
  }

  const { totals } = progress;
  const practised = totals.turns > 0 || totals.attempts > 0;

  return (
    <Page width="full" className="gap-6">
      <PageHeader
        title="Your progress"
        description={`Weeks from ${progress.since} to ${progress.until}. Every figure is
          counted from what you recorded — nothing on this page is written by a language
          model.`}
        actions={<RefreshProgress stale={progress.stale} />}
      />

      {progress.stale && (
        <Alert>
          <AlertDescription>
            Something has been analysed or scored since these figures were last computed,
            so they are behind your practice. Rebuilding takes a moment.
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardContent className="flex flex-wrap items-center gap-8 py-5">
          <Figure label="conversations" value={String(totals.sessions)} />
          <Figure label="turns you spoke" value={String(totals.turns)} />
          <Figure label="words" value={String(totals.words)} />
          <Figure label="scored readings" value={String(totals.attempts)} />
          <Figure label="sounds scored" value={String(totals.phones)} />
          <Badge variant="outline" className="ml-auto">
            {totals.periods} week{totals.periods === 1 ? "" : "s"} with practice in them
          </Badge>
        </CardContent>
      </Card>

      {!practised && (
        <Card>
          <CardContent className="flex flex-col items-start gap-3 py-6">
            <p className="text-sm text-muted-foreground">
              There is nothing to chart yet. One conversation produces corrections, forms
              and timings; one reading produces per-sound scores.
            </p>
            <div className="flex gap-2">
              <Button asChild>
                <Link href="/scenarios">Choose a scenario</Link>
              </Button>
              <Button asChild variant="outline">
                <Link href="/read">Read a passage</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Two columns from `xl` up, one below it. The panels are independent of each
          other — a fluency trend says nothing about an accuracy trend — so stacking
          them in a single column on a wide display buys nothing and costs a scroll
          past four cards to reach the fifth. */}
      <div className="grid gap-6 xl:grid-cols-2">
        <NextUpCard recommendations={recommendations} />

        {progress.families.map((family) => (
          <MetricPanel key={family.name} family={family} />
        ))}

        <RepertoireChart repertoire={progress.repertoire} />
      </div>

      {/* Full width on its own: one row per sound, and there are up to forty of them. */}
      <PhonemeTrend phones={progress.phones} gate={progress.phone_gate} />
    </Page>
  );
}
