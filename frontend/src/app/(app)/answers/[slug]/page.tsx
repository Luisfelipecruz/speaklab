/**
 * One question: read it, answer it out loud, and see the answer counted — or say an earlier
 * answer again and see the two side by side.
 *
 * The earlier answers to the question are listed under the recorder, newest first, each
 * with *Say this one again*, which opens this page with that answer as the one to beat —
 * not a target, the same counts beside each other.
 *
 * Server-rendered with the cookie forwarded; the recorder is the one client component.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Repeat2 } from "lucide-react";

import { AnswerRecorder } from "@/components/AnswerRecorder";
import { Page, PageHeader } from "@/components/PageHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AnswersPage } from "@/lib/api";
import { CATEGORY_LABEL, clock } from "@/lib/answers";
import { serverRequestOrNull } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Make your point — SpeakLab" };

export default async function AnswerPromptPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ again?: string }>;
}) {
  const [{ slug }, { again }] = await Promise.all([params, searchParams]);
  if (!/^[a-z0-9-]+$/.test(slug)) notFound();

  // Null is 401 or 404; the page says both in one sentence.
  const page = await serverRequestOrNull<AnswersPage>(`/answers?prompt=${slug}`);

  if (!page || !page.prompt) {
    return (
      <Page>
        <Alert className="w-fit max-w-2xl">
          <AlertDescription>
            That question is not available. You may need to{" "}
            <Link href={`/login?next=/answers/${slug}`} className="underline">
              sign in
            </Link>
            .
          </AlertDescription>
        </Alert>
      </Page>
    );
  }

  const prompt = page.prompt;
  const basis = again ? (page.answers.find((answer) => answer.id === Number(again)) ?? null) : null;

  return (
    <Page className="gap-6">
      <PageHeader
        eyebrow={
          <>
            <Badge variant="secondary">{prompt.cefr_band}</Badge>
            <span className="text-sm text-muted-foreground">{CATEGORY_LABEL[prompt.category]}</span>
            <span className="text-sm text-muted-foreground tabular-nums">
              up to {clock(prompt.time_limit_s * 1000)}
            </span>
          </>
        }
        title={prompt.title}
        description={prompt.prompt}
      />
      <div className="flex w-full max-w-4xl flex-col gap-6">
        <Button asChild variant="ghost" size="sm" className="w-fit">
          <Link href="/answers">
            <ArrowLeft aria-hidden="true" />
            All questions
          </Link>
        </Button>

        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium text-muted-foreground">
              Answer out loud, in one go
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <p className="max-w-[64ch] text-sm text-muted-foreground">
              Say the main point first. Then give a reason or an example for each thing you
              say, and finish by saying the point again in a sentence.
            </p>
            {/* Keyed on the answer being said again, so choosing another starts afresh. */}
            <AnswerRecorder key={basis?.id ?? "new"} prompt={prompt} basis={basis} />
          </CardContent>
        </Card>

        {page.answers.length > 0 && (
          <section className="flex flex-col gap-3" aria-labelledby="earlier">
            <h2 id="earlier" className="text-lg font-semibold tracking-tight">
              Your earlier answers to this question
            </h2>
            <ul className="flex flex-col gap-3">
              {page.answers.map((answer) => (
                <li
                  key={answer.id}
                  className="flex flex-col gap-2 rounded-lg border border-border p-4"
                  data-testid={`earlier-${answer.id}`}
                >
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground tabular-nums">
                    <span>{answer.created_at.slice(0, 16).replace("T", " ")}</span>
                    <span>
                      {answer.delivery.words} words in {clock(answer.delivery.duration_ms)}
                    </span>
                    {answer.structure.sentences !== null && (
                      <span>{answer.structure.sentences} sentences</span>
                    )}
                    {answer.again_of && <Badge variant="outline">said again</Badge>}
                    <Button asChild variant="outline" size="sm" className="ml-auto">
                      <Link href={`/answers/${prompt.slug}?again=${answer.id}`}>
                        <Repeat2 aria-hidden="true" />
                        Say this one again
                      </Link>
                    </Button>
                  </div>
                  <p className="line-clamp-3 text-sm">{answer.transcript}</p>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </Page>
  );
}
