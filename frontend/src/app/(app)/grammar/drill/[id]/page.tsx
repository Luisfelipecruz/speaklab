/**
 * Say it again: one of your corrections, practised aloud.
 *
 * Reached from a correction on the grammar page. The page reads the correction first —
 * the sentence as you said it, what was proposed and by what — then the sentence to say,
 * with the correction in it, and the button. What comes back is what the recogniser
 * heard, word by word; nothing is scored and nothing is stored.
 *
 * **Skipping is part of the drill.** The corrections are often wrong, and practising a
 * wrong one practises the mistake, so the way on to the next correction of the same kind
 * is always on the page, before the button as well as after it.
 *
 * Server-rendered with the cookie forwarded, like every signed-in page; the recorder is
 * the one client component.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight, Info } from "lucide-react";

import { DrillCorrectionCard } from "@/components/DrillCorrectionCard";
import { DrillRecorder } from "@/components/DrillRecorder";
import { DrillSentence } from "@/components/DrillSentence";
import { Page, PageHeader } from "@/components/PageHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Drill } from "@/lib/api";
import { serverRequestOrNull } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Say it again — SpeakLab" };

export default async function DrillPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const correctionId = Number(id);
  if (!Number.isInteger(correctionId) || correctionId <= 0) notFound();

  // Null is 401 or 404, and the two are not told apart on screen: somebody else's
  // correction is a 404 so that guessing an id says nothing.
  const drill = await serverRequestOrNull<Drill>(`/corrections/${correctionId}/drill`);

  if (!drill) {
    return (
      <Page>
        <Alert className="w-fit max-w-2xl">
          <AlertDescription>
            That correction is not available. It may belong to another account, or you may
            need to{" "}
            <Link href={`/login?next=/grammar/drill/${correctionId}`} className="underline">
              sign in
            </Link>
            .
          </AlertDescription>
        </Alert>
      </Page>
    );
  }

  const practised = drill.corrections.find((c) => c.id === drill.id) ?? drill.corrections[0];
  const onward = (
    <div className="flex flex-wrap items-center gap-2">
      <Button asChild variant="ghost" size="sm">
        <Link href="/grammar">
          <ArrowLeft aria-hidden="true" />
          Your corrections
        </Link>
      </Button>
      {drill.next_id !== null && (
        <Button asChild variant="outline" size="sm">
          <Link href={`/grammar/drill/${drill.next_id}`}>
            Skip to the next {practised.label} correction
            <ArrowRight aria-hidden="true" />
          </Link>
        </Button>
      )}
    </div>
  );

  return (
    <Page className="gap-6">
      <PageHeader
        title="Say it again"
        description="One of your own sentences, with its correction in it. Say it the corrected way, and see what the recogniser heard."
      />
      {/* The frame keeps the shell's measure; a sentence to read aloud reads best narrower. */}
      <div className="flex w-full max-w-3xl flex-col gap-6">
        {onward}
        <DrillCorrectionCard drill={drill} />

        {drill.unavailable ? (
          <Alert>
            <AlertDescription>{drill.unavailable}</AlertDescription>
          </Alert>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-medium text-muted-foreground">
                Say this
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-6">
              <DrillSentence drill={drill} as="say" className="text-lg tracking-[-0.005em]" />
              <DrillRecorder drill={drill} />
            </CardContent>
          </Card>
        )}

        <p
          className="flex gap-2 rounded-lg border border-chart-2/40 bg-chart-2/10 p-3 text-sm leading-relaxed"
          data-testid="drill-caveat"
        >
          <Info className="mt-1 size-4 shrink-0 text-chart-2" aria-hidden="true" />
          <span>{drill.caveat}</span>
        </p>
        {drill.next_id === null && (
          <p className="text-sm text-muted-foreground">
            That is the last {practised.label} correction to say again.
          </p>
        )}
      </div>
    </Page>
  );
}
