/**
 * Where signing in lands you: how you are doing, and what to do about it.
 *
 * Sign-in used to drop a person on the scenario catalogue — eight cards, none of which
 * knows anything about them. Every number needed to answer "how am I doing, and what
 * should I do now" was already being computed; nothing was putting it in front of the
 * person on their way in.
 *
 * **Nothing here is new.** The recommendation card, the counts and the last conversations
 * are the same three responses the progress and history pages read, arranged for somebody
 * arriving rather than somebody investigating. No figure on this page is written by a
 * language model — the ranking is a weighted score over stored rows, and the counts are
 * counted.
 *
 * **The empty state is the first state and it is designed rather than defaulted.** A new
 * account has no trend, no recommendation worth the name and no history, and a page that
 * renders three empty cards for it says "this product is broken" rather than "you have
 * not started yet".
 */

import Link from "next/link";
import { HistoryIcon, MicIcon, MessagesSquareIcon } from "lucide-react";

import { NextUpCard } from "@/components/NextUpCard";
import { Page, PageHeader } from "@/components/PageHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Progress, Recommendations, SessionPage } from "@/lib/api";
import { serverRequestOrNull } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Home — SpeakLab" };

function when(iso: string): string {
  // Fixed locale and time zone, not the viewer's — a server-rendered date formatted in
  // the server's locale and re-rendered in the browser's is the classic hydration
  // mismatch, and it shows up as a date that flickers on load.
  return new Date(iso).toISOString().slice(0, 16).replace("T", " ");
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-2xl font-semibold tabular-nums">{value}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

export default async function HomePage() {
  const [progress, recommendations, history] = await Promise.all([
    serverRequestOrNull<Progress>("/progress"),
    serverRequestOrNull<Recommendations>("/progress/recommendations"),
    serverRequestOrNull<SessionPage>("/sessions?limit=3"),
  ]);

  if (!progress) {
    return (
      <Page>
        <PageHeader
          title="SpeakLab"
          description="Practise spoken English against models running on this machine."
        />
        <Alert>
          <AlertDescription>
            <Link href="/login?next=/home" className="underline">
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

  if (!practised) {
    return (
      <Page>
        <PageHeader
          title="Start here"
          description="Nothing has been recorded on this account yet, so there is nothing to
            measure. Two things produce something worth looking at."
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <StartCard
            icon={<MessagesSquareIcon className="size-5" />}
            title="Have a conversation"
            description="A role-play with a goal and a persona who pushes back. You speak,
              it answers out loud, and at the end you get a report of what happened."
            href="/scenarios"
            action="Choose a scenario"
          />
          <StartCard
            icon={<MicIcon className="size-5" />}
            title="Read a passage aloud"
            description="Each passage is built to force one group of sounds. Every sound
              you make is scored against the one the text asked for."
            href="/read"
            action="Choose a passage"
          />
        </div>

        <p className="text-sm text-muted-foreground">
          You will need a microphone and about ten minutes. Nothing you say leaves this
          machine.
        </p>
      </Page>
    );
  }

  return (
    <Page>
      <PageHeader
        title="Your practice"
        description={`Counted from what you recorded, ${progress.since} to ${progress.until}.`}
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/progress">See the trends</Link>
          </Button>
        }
      />

      <Card>
        <CardContent className="flex flex-wrap items-center gap-x-10 gap-y-4 py-5">
          <Figure label="conversations" value={String(totals.sessions)} />
          <Figure label="turns you spoke" value={String(totals.turns)} />
          <Figure label="words" value={String(totals.words)} />
          <Figure label="scored readings" value={String(totals.attempts)} />
          <Badge variant="outline" className="ml-auto">
            {totals.periods} week{totals.periods === 1 ? "" : "s"} with practice in them
          </Badge>
        </CardContent>
      </Card>

      {progress.stale && (
        <Alert>
          <AlertDescription>
            Something has been analysed or scored since these figures were computed.{" "}
            <Link href="/progress" className="underline">
              Rebuild them on the progress page.
            </Link>
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {recommendations && <NextUpCard recommendations={recommendations} />}

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <HistoryIcon className="size-4" />
              Where you left off
            </CardTitle>
            <CardDescription>
              The last conversations on this account, newest first.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {history && history.items.length > 0 ? (
              <>
                <ul className="flex flex-col gap-3">
                  {history.items.map((session) => (
                    <li key={session.id} className="flex items-center justify-between gap-4">
                      <div className="flex min-w-0 flex-col gap-0.5">
                        <Link
                          href={`/sessions/${session.id}`}
                          className="truncate font-medium hover:underline"
                        >
                          {session.scenario_title ?? "Read-aloud session"}
                        </Link>
                        <span className="text-xs text-muted-foreground">
                          {when(session.started_at)} · {session.turn_count} turns
                        </span>
                      </div>
                      <Badge
                        variant={session.status === "active" ? "default" : "secondary"}
                      >
                        {session.status}
                      </Badge>
                    </li>
                  ))}
                </ul>
                <Button asChild variant="link" size="sm" className="h-auto w-fit p-0">
                  <Link href="/sessions">All {history.total} conversations</Link>
                </Button>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                Nothing recorded yet. A reading is scored without a conversation, which is
                why the counts above can move while this stays empty.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </Page>
  );
}

function StartCard({
  icon,
  title,
  description,
  href,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  href: string;
  action: string;
}) {
  return (
    <Card className="flex flex-col">
      <CardHeader className="gap-2">
        <CardTitle className="flex items-center gap-2 text-base">
          {icon}
          {title}
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="mt-auto">
        <Button asChild>
          <Link href={href}>{action}</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
