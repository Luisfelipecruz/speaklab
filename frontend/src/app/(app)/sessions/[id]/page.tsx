/**
 * One conversation.
 *
 * **Server-rendered first, then handed to the client.** The transcript is fetched here,
 * with the browser's cookie forwarded, so a page reload paints the conversation rather
 * than a spinner over it: a session that survives a reload is one that is *on the screen*
 * after the reload, not one that can be fetched a round trip later.
 *
 * The client component below takes that snapshot as its initial state and never refetches
 * on mount, so the first paint and the interactive state are the same conversation and
 * not two.
 *
 * **Two kinds of session arrive here, and only one of them is a conversation.**
 * Read-aloud groups several readings of a passage into a sitting — a `sessions` row with
 * no scenario and no turns. Rendering that through `Conversation` would produce a page
 * with an empty transcript and a record button whose only possible outcome is a 409
 * saying the session has no conversation to continue. So the mode is branched on before
 * anything is rendered.
 */

import Link from "next/link";
import { notFound } from "next/navigation";

import { Conversation } from "@/app/(app)/sessions/[id]/Conversation";
import { Page, PageHeader } from "@/components/PageHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { AttemptPage, SessionDetail } from "@/lib/api";
import { serverRequestOrNull } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export default async function SessionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const sessionId = Number(id);
  if (!Number.isInteger(sessionId) || sessionId <= 0) notFound();

  // Null here means 401 or 404 and the two are deliberately not distinguished on
  // screen: the API answers 404 for somebody else's session precisely so that guessing
  // an id tells you nothing, and a frontend that said "you are not allowed to see
  // session 41" would hand back the fact the server withheld.
  const session = await serverRequestOrNull<SessionDetail>(`/sessions/${sessionId}`);

  if (!session) {
    return (
      <Page>
        <Alert>
          <AlertDescription>
            That conversation is not available. It may belong to another account, or you
            may need to{" "}
            <Link href={`/login?next=/sessions/${sessionId}`} className="underline">
              sign in
            </Link>
            .
          </AlertDescription>
        </Alert>
      </Page>
    );
  }

  if (session.mode === "read_aloud") {
    return <ReadingSitting sessionId={sessionId} startedAt={session.started_at} />;
  }

  return <Conversation sessionId={sessionId} initial={session} />;
}

/**
 * A read-aloud sitting: the readings taken in it, newest first.
 *
 * Deliberately not a second copy of the scoring screen. The place to look at one reading
 * in detail is the passage page, which has the passage text to tint; this is the index
 * into a sitting, so each row carries the two numbers that say whether the reading is
 * worth opening — how far it drifted from the text, and how many sounds were scored.
 */
async function ReadingSitting({
  sessionId,
  startedAt,
}: {
  sessionId: number;
  startedAt: string;
}) {
  const page = await serverRequestOrNull<AttemptPage>(
    `/attempts?session_id=${sessionId}&limit=50`,
  );
  const readings = page?.items ?? [];

  return (
    <Page className="gap-6">
      <PageHeader
        eyebrow={
          <>
            <Badge variant="secondary">Read aloud</Badge>
            <span className="text-xs text-muted-foreground">
              {new Date(startedAt).toLocaleString()}
            </span>
          </>
        }
        title={readings.length === 1 ? "One reading" : `${readings.length} readings`}
      />

      {readings.length === 0 ? (
        <Alert className="w-fit max-w-2xl">
          <AlertDescription>
            This sitting has no readings in it. Start one from{" "}
            <Link href="/read" className="underline">
              read aloud
            </Link>
            .
          </AlertDescription>
        </Alert>
      ) : (
        /* One card, one row per reading — the same list the history page draws, so
           the two screens that list sittings look like the same product. */
        <Card className="max-w-3xl py-0">
          <ul className="divide-y divide-border">
            {readings.map((reading) => (
              <li key={reading.id} className="flex flex-col gap-2 px-5 py-4">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <Link
                    href={`/read/${reading.passage_slug}`}
                    className="text-base font-semibold hover:text-primary"
                  >
                    {reading.passage_title ?? reading.passage_slug}
                  </Link>
                  <span className="text-xs text-muted-foreground">
                    {new Date(reading.created_at).toLocaleString()}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-4 text-sm">
                {reading.wer !== null && (
                  <span className="text-muted-foreground">
                    Word error rate{" "}
                    <strong className="text-foreground">
                      {(reading.wer * 100).toFixed(0)}%
                    </strong>
                  </span>
                )}
                <span className="text-muted-foreground">
                  {reading.phoneme_count > 0 ? (
                    <>
                      <strong className="text-foreground">
                        {reading.phoneme_count}
                      </strong>{" "}
                      sounds scored
                    </>
                  ) : reading.status === "scored" ? (
                    "not scored — the pronunciation service was not running"
                  ) : (
                    reading.status
                  )}
                </span>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </Page>
  );
}
