/**
 * Grammar: your own sentences, the corrections proposed for them, and the verb forms they
 * were in.
 *
 * **A page of evidence rather than a grade.** Every correction on it was proposed by
 * grammar rules or a language model, and none was checked by a person. So it leads with
 * the sentences — each marked where the correction is, with what was proposed instead and
 * a link to the conversation it came from — and the verb forms carry counts with the
 * corrections behind them. There is no percentage anywhere on it: a percentage cannot be
 * disagreed with, and a correction can.
 *
 * **Its own section, not a tab of progress.** Progress says whether you are getting
 * better, from snapshots drawn as trends. This says what to practise, and it is read from
 * the corrections themselves, because a snapshot holds no sentences.
 *
 * Server-rendered with the cookie forwarded, like every signed-in page.
 */

import Link from "next/link";
import { Info } from "lucide-react";

import { FormPracticeList } from "@/components/FormPracticeList";
import { GrammarCategory } from "@/components/GrammarCategory";
import { Page, PageHeader } from "@/components/PageHeader";
import { WeakestFormCard } from "@/components/WeakestFormCard";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { GrammarPage as GrammarPageShape } from "@/lib/api";
import { serverRequestOrNull } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Grammar — SpeakLab" };

export default async function GrammarPage() {
  const page = await serverRequestOrNull<GrammarPageShape>("/grammar");

  if (!page) {
    return (
      <Page>
        <Alert className="w-fit max-w-2xl">
          <AlertDescription>
            <Link href="/login?next=/grammar" className="underline">
              Sign in
            </Link>{" "}
            to see the corrections proposed for what you said.
          </AlertDescription>
        </Alert>
      </Page>
    );
  }

  const { totals } = page;

  return (
    <Page className="gap-6">
      <PageHeader
        title="Grammar"
        description={`Your own sentences from ${page.since} to ${page.until}, the corrections
          proposed for them, and the verb forms they were in.`}
      />

      {totals.turns === 0 ? (
        <Card className="max-w-2xl">
          <CardContent className="flex flex-col items-start gap-3 py-2">
            <p className="text-sm text-muted-foreground">
              Nothing you have said has been analysed yet. A conversation is where the
              corrections come from, and each one appears here in the sentence you said it
              in.
            </p>
            <Button asChild>
              <Link href="/scenarios">Choose a scenario</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <p className="text-sm text-muted-foreground tabular-nums">
            {totals.corrections} correction{totals.corrections === 1 ? "" : "s"} in{" "}
            {totals.words} words, across {totals.turns} turn{totals.turns === 1 ? "" : "s"}{" "}
            in {totals.sessions} conversation{totals.sessions === 1 ? "" : "s"}.
          </p>

          {page.caveat && (
            <p
              className="flex max-w-3xl gap-2 rounded-lg border border-chart-2/40 bg-chart-2/10 p-3 text-sm leading-relaxed"
              data-testid="grammar-caveat"
            >
              <Info className="mt-1 size-4 shrink-0 text-chart-2" aria-hidden="true" />
              <span>{page.caveat}</span>
            </p>
          )}

          <WeakestFormCard weakest={page.weakest} gate={page.weakest_gate} />

          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
            <section className="flex flex-col gap-4" aria-labelledby="by-kind">
              <h2 id="by-kind" className="text-lg font-semibold tracking-tight">
                Your corrections, by kind
              </h2>
              {page.categories.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Nothing was flagged in {totals.words} words. That is not the same as no
                  mistakes: the detector misses many of them.
                </p>
              ) : (
                page.categories.map((category) => (
                  <GrammarCategory key={category.category} category={category} />
                ))
              )}
            </section>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  <h2>The verb forms you used</h2>
                </CardTitle>
                <CardDescription>
                  How often each was right, out of the times you said it and the times it
                  was needed and you said something else — with the corrections behind the
                  count.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <FormPracticeList forms={page.forms} />
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </Page>
  );
}
