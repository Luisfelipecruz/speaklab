/**
 * Whether you are getting better, and what to practise next.
 *
 * **One family at a time.** All four families at once is eleven series, and for an account
 * with a few weeks of practice every one of them holds a single measurement — eleven
 * near-empty charts and fifty-odd figures, which reads as a control panel rather than as
 * an answer. The families are independent of each other anyway: a fluency trend says
 * nothing about an accuracy trend, so there is nothing to compare across them and no
 * reason to make somebody scroll past four to reach the fifth. The section is in the URL,
 * so a tab is shareable and the back button works.
 *
 * **The overview is the answer, not a summary of the charts.** It says how much practice
 * the figures stand on, what to do next, and one line per family saying whether it has
 * anything to show — which is the question somebody arriving actually has.
 *
 * **The empty state is the main state, and it is designed rather than defaulted.** A new
 * account has nothing here, and so does an account with a fortnight of occasional
 * practice — which is most of them, for months. So every suppressed chart says what it is
 * waiting for. Blank axes with no explanation read as a broken feature; "three more
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
import { familyStatus } from "@/app/(app)/progress/summary";
import { SectionTabs } from "@/components/SectionTabs";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { Progress, Recommendations } from "@/lib/api";
import { serverRequestOrNull } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Progress — SpeakLab" };

const OVERVIEW = "overview";

/** One large number and what it counts. The figures are the reason for the page. */
function Figure({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-3xl font-semibold tabular-nums">{value}</span>
      <span className="text-sm text-muted-foreground">{label}</span>
    </div>
  );
}

export default async function ProgressPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string }>;
}) {
  const [progress, recommendations, params] = await Promise.all([
    serverRequestOrNull<Progress>("/progress"),
    serverRequestOrNull<Recommendations>("/progress/recommendations"),
    searchParams,
  ]);

  if (!progress || !recommendations) {
    return (
      <Page>
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

  // An unknown `?view=` falls back to the overview rather than rendering an empty page.
  const known = new Set([OVERVIEW, ...progress.families.map((family) => family.name)]);
  const view = params.view && known.has(params.view) ? params.view : OVERVIEW;
  const family = progress.families.find((candidate) => candidate.name === view);

  const sections = [
    { key: OVERVIEW, label: "Overview", href: "/progress" },
    ...progress.families.map((candidate) => ({
      key: candidate.name,
      label: candidate.label,
      href: `/progress?view=${candidate.name}`,
    })),
  ];

  return (
    <Page className="gap-6">
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

      <SectionTabs label="Progress sections" sections={sections} current={view} />

      {view === OVERVIEW ? (
        <div className="flex flex-col gap-6">
          <Card>
            <CardContent className="flex flex-wrap items-start gap-x-12 gap-y-6 py-6">
              <Figure label="conversations" value={totals.sessions} />
              <Figure label="turns you spoke" value={totals.turns} />
              <Figure label="words" value={totals.words} />
              <Figure label="scored readings" value={totals.attempts} />
              <Figure label="sounds scored" value={totals.phones} />
              <Figure
                label={`week${totals.periods === 1 ? "" : "s"} with practice in them`}
                value={totals.periods}
              />
            </CardContent>
          </Card>

          {!practised && (
            <Card>
              <CardContent className="flex flex-col items-start gap-3 py-6">
                <p className="text-sm text-muted-foreground">
                  There is nothing to chart yet. One conversation produces corrections,
                  forms and timings; one reading produces per-sound scores.
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

          <div className="grid gap-6 lg:grid-cols-2">
            <NextUpCard recommendations={recommendations} />

            <Card>
              <CardContent className="flex flex-col gap-1 py-2">
                {progress.families.map((candidate) => (
                  <Link
                    key={candidate.name}
                    href={`/progress?view=${candidate.name}`}
                    className="flex flex-col gap-0.5 rounded-md px-3 py-3 transition-colors hover:bg-muted"
                  >
                    <span className="text-sm font-medium">{candidate.label}</span>
                    <span className="text-xs text-muted-foreground">
                      {familyStatus(candidate)}
                    </span>
                  </Link>
                ))}
              </CardContent>
            </Card>
          </div>
        </div>
      ) : (
        family && (
          <div className="flex flex-col gap-6">
            <MetricPanel family={family} />

            {/* Breadth belongs with the family it qualifies: the point of counting forms
                is that a narrowing range lowers an error rate without anybody improving,
                and the two only mean something read together. */}
            {family.name === "complexity" && (
              <RepertoireChart repertoire={progress.repertoire} />
            )}

            {family.name === "pronunciation" && (
              <PhonemeTrend phones={progress.phones} gate={progress.phone_gate} />
            )}
          </div>
        )
      )}
    </Page>
  );
}
