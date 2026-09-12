/**
 * Make your point: pick a work question, answer it out loud, and see it counted.
 *
 * **The questions first, grouped by what they ask for** — explain, justify, walk someone
 * through, recommend — because the kind of answer decides which signposts it needs, and a
 * learner practising walk-throughs is practising steps.
 *
 * **Then the answers over time**, one point per answer in the progress page's charts and
 * by its rule: only fewer fillers and fewer words said twice are ever called improving,
 * because nothing else counted here has a better end.
 *
 * Server-rendered with the cookie forwarded, like every signed-in page.
 */

import Link from "next/link";
import { Info } from "lucide-react";

import { Page, PageHeader } from "@/components/PageHeader";
import { TrendChart } from "@/components/TrendChart";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { AnswersPage as AnswersPageShape } from "@/lib/api";
import { CATEGORY_LABEL, CATEGORY_ORDER, answeredLabel, clock } from "@/lib/answers";
import { serverRequestOrNull } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Make your point — SpeakLab" };

export default async function AnswersPage() {
  const page = await serverRequestOrNull<AnswersPageShape>("/answers");

  if (!page) {
    return (
      <Page>
        <Alert className="w-fit max-w-2xl">
          <AlertDescription>
            <Link href="/login?next=/answers" className="underline">
              Sign in
            </Link>{" "}
            to answer a question out loud.
          </AlertDescription>
        </Alert>
      </Page>
    );
  }

  const drawn = page.history.filter((series) => series.gate.shown);

  return (
    <Page className="gap-8">
      <PageHeader
        title="Make your point"
        description="Answer a work question out loud, in one go. How you built the answer and
          how you said it are counted from the recording, and a language model's feedback
          sits beside the counts."
      />

      <section className="flex flex-col gap-6" aria-labelledby="questions">
        <h2 id="questions" className="text-lg font-semibold tracking-tight">
          Choose a question
        </h2>
        {CATEGORY_ORDER.map((category) => {
          const prompts = page.prompts.filter((prompt) => prompt.category === category);
          if (prompts.length === 0) return null;
          return (
            <div key={category} className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold text-muted-foreground">
                {CATEGORY_LABEL[category]}
              </h3>
              <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {prompts.map((prompt) => (
                  <li key={prompt.slug}>
                    <Link
                      href={`/answers/${prompt.slug}`}
                      className="group block h-full rounded-xl border border-border bg-card p-4 transition-colors hover:border-primary"
                    >
                      <span className="flex items-center gap-2 text-xs text-muted-foreground">
                        <Badge variant="secondary">{prompt.cefr_band}</Badge>
                        <span className="tabular-nums">{clock(prompt.time_limit_s * 1000)}</span>
                        <span className="ml-auto">{answeredLabel(prompt.answers)}</span>
                      </span>
                      <span className="mt-2 block font-semibold group-hover:text-primary">
                        {prompt.title}
                      </span>
                      <span className="mt-1 block text-sm text-muted-foreground">{prompt.prompt}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </section>

      <section className="flex flex-col gap-4" aria-labelledby="over-time">
        <h2 id="over-time" className="text-lg font-semibold tracking-tight">
          Your answers over time
        </h2>
        {page.answered === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing answered yet. Each answer you give adds a point to every chart here.
          </p>
        ) : (
          <>
            <p className="flex max-w-3xl gap-2 rounded-lg border border-chart-2/40 bg-chart-2/10 p-3 text-sm leading-relaxed">
              <Info className="mt-1 size-4 shrink-0 text-chart-2" aria-hidden="true" />
              <span>{page.caveat}</span>
            </p>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {drawn.map((series) => (
                <Card key={series.metric}>
                  <CardContent className="py-4">
                    <TrendChart series={series} per="answer" />
                  </CardContent>
                </Card>
              ))}
            </div>
            {page.history
              .filter((series) => !series.gate.shown)
              .map((series) => (
                <p key={series.metric} className="text-sm text-muted-foreground">
                  {series.label}: {series.gate.reason}
                </p>
              ))}
          </>
        )}
      </section>

      {page.answers.length > 0 && (
        <section className="flex flex-col gap-3" aria-labelledby="latest">
          <h2 id="latest" className="text-lg font-semibold tracking-tight">
            Your latest answers
          </h2>
          <div className="grid gap-3 md:grid-cols-3">
            {page.answers.map((answer) => (
              <Card key={answer.id}>
                <CardHeader>
                  <CardTitle className="text-sm">
                    <Link href={`/answers/${answer.prompt.slug}`} className="hover:text-primary">
                      {answer.prompt.title}
                    </Link>
                  </CardTitle>
                  <CardDescription className="tabular-nums">
                    {answer.created_at.slice(0, 10)} · {answer.delivery.words} words in{" "}
                    {clock(answer.delivery.duration_ms)}
                  </CardDescription>
                </CardHeader>
                <CardContent className="line-clamp-3 text-sm text-muted-foreground">
                  {answer.transcript}
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      )}
    </Page>
  );
}
