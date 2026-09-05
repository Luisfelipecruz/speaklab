/**
 * One scenario, and the button that starts a conversation with it.
 *
 * The brief is shown in full — the goal and the rubric criteria — because telling a
 * learner what finishing looks like and what is being assessed is not a spoiler, it is
 * the exercise. `persona_prompt` is the opposite: it is the interviewer's private
 * instructions, and the API does not serve it at all, so there is nothing to withhold
 * here.
 *
 * Server-rendered, with one client island for the start button, because starting a
 * session is a POST that needs the session cookie from the browser.
 */

import { notFound } from "next/navigation";

import { StartSession } from "@/app/(app)/scenarios/[slug]/StartSession";
import { Page } from "@/components/PageHeader";
import { humanise } from "@/components/ScenarioCard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, type ScenarioDetail } from "@/lib/api";
import { serverRequest } from "@/lib/server-api";

export const dynamic = "force-dynamic";

// Static, not a `generateMetadata` that names the scenario. Producing the title would
// mean fetching the scenario a second time — `serverRequest` sends `cache: "no-store"`,
// so Next has nothing to deduplicate against — and a second round trip per page view is
// a poor trade for a browser tab label.
export const metadata = { title: "Scenario — SpeakLab" };

export default async function ScenarioPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  let scenario: ScenarioDetail;
  try {
    scenario = await serverRequest<ScenarioDetail>(`/scenarios/${encodeURIComponent(slug)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const criteria = scenario.rubric.criteria ?? [];

  return (
    <Page>
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{scenario.cefr_band}</Badge>
          <Badge variant="outline">{humanise(scenario.category)}</Badge>
        </div>
        <h1 className="text-3xl font-semibold tracking-tight">{scenario.title}</h1>
        <p className="text-muted-foreground">{scenario.description}</p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Your goal</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-sm leading-relaxed">{scenario.goal}</p>

          {criteria.length > 0 && (
            <div className="flex flex-col gap-2">
              <h3 className="text-xs font-medium text-muted-foreground">
                What the end-of-session report looks at
              </h3>
              <ul className="flex flex-col gap-1.5 text-sm">
                {criteria.map((criterion) => (
                  <li key={criterion.name}>
                    <span className="font-medium">{humanise(criterion.name)}</span>
                    <span className="text-muted-foreground"> — {criterion.descriptor}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {scenario.target_grammar.length > 0 && (
            <div className="flex flex-col gap-2">
              <h3 className="text-xs font-medium text-muted-foreground">
                Forms this scenario is built to draw out
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {scenario.target_grammar.map((form) => (
                  <Badge key={form} variant="outline" className="font-normal">
                    {humanise(form)}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <StartSession slug={scenario.slug} title={scenario.title} />
    </Page>
  );
}
