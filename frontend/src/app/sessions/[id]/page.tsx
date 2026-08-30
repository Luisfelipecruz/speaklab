/**
 * One conversation. FR-10.
 *
 * **Server-rendered first, then handed to the client.** The transcript is fetched here,
 * with the browser's cookie forwarded, so a page reload paints the conversation rather
 * than a spinner over it. That is what FR-10 is actually asking for: a session that
 * survives a reload is one that is *on the screen* after the reload, not one that can be
 * fetched a round trip later.
 *
 * The client component below takes that snapshot as its initial state and never refetches
 * on mount, so the first paint and the interactive state are the same conversation and
 * not two.
 */

import Link from "next/link";
import { notFound } from "next/navigation";

import { Conversation } from "@/app/sessions/[id]/Conversation";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { SessionDetail } from "@/lib/api";
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
  // an id tells you nothing (D25), and a frontend that said "you are not allowed to see
  // session 41" would hand back the fact the server withheld.
  const session = await serverRequestOrNull<SessionDetail>(`/sessions/${sessionId}`);

  if (!session) {
    return (
      <Alert>
        <AlertDescription>
          That conversation is not available. It may belong to another account, or you may
          need to{" "}
          <Link href={`/login?next=/sessions/${sessionId}`} className="underline">
            sign in
          </Link>
          .
        </AlertDescription>
      </Alert>
    );
  }

  return <Conversation sessionId={sessionId} initial={session} />;
}
