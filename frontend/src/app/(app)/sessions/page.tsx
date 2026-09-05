/**
 * Everything you have practised, newest first.
 *
 * Without this page a conversation is unreachable the moment the tab is closed, which
 * would make "a session survives a page reload" true of the API and false of the product.
 * It is one server-rendered list and one client button.
 *
 * Paginated because the endpoint is. Eight scenarios are eight scenarios forever, but
 * history is the one list here that grows without bound, and a page that reads a year of
 * it into memory is a page that works for exactly as long as the demo.
 */

import Link from "next/link";

import { DeleteSessionButton } from "@/app/(app)/sessions/DeleteSessionButton";
import { Page, PageHeader } from "@/components/PageHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { SessionPage } from "@/lib/api";
import { serverRequestOrNull } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export const metadata = { title: "History — SpeakLab" };

const PAGE_SIZE = 20;

function when(iso: string): string {
  // Fixed locale and time zone, not the viewer's. A server-rendered date formatted in
  // the server's locale and then re-rendered in the browser's is the classic hydration
  // mismatch, and it shows up as a date that flickers on load.
  return new Date(iso).toISOString().slice(0, 16).replace("T", " ");
}

export default async function SessionsPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string }>;
}) {
  const { offset: rawOffset } = await searchParams;
  const offset = Math.max(0, Number(rawOffset ?? 0) || 0);

  const page = await serverRequestOrNull<SessionPage>(
    `/sessions?limit=${PAGE_SIZE}&offset=${offset}`,
  );

  if (!page) {
    return (
      <Page>
        <Alert>
          <AlertDescription>
            <Link href="/login?next=/sessions" className="underline">
              Sign in
            </Link>{" "}
            to see the conversations you have practised.
          </AlertDescription>
        </Alert>
      </Page>
    );
  }

  return (
    <Page>
      <PageHeader
        title="Your conversations"
        description={
          page.total === 0
            ? "Nothing yet."
            : `${page.total} session${page.total === 1 ? "" : "s"}, newest first.`
        }
      />

      {page.items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-start gap-3 py-6">
            <p className="text-sm text-muted-foreground">
              You have not practised anything yet.
            </p>
            <Button asChild>
              <Link href="/scenarios">Choose a scenario</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <ul className="flex flex-col gap-3">
          {page.items.map((session) => (
            <li key={session.id}>
              <Card className="relative">
                <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
                  <div className="flex flex-col gap-1">
                    <Link
                      href={`/sessions/${session.id}`}
                      className="font-medium after:absolute after:inset-0 hover:underline"
                    >
                      {session.scenario_title ?? "Read-aloud session"}
                    </Link>
                    <span className="text-xs text-muted-foreground">
                      {when(session.started_at)} · {session.turn_count} turns
                    </span>
                  </div>

                  <div className="relative flex items-center gap-2">
                    <Badge variant={session.status === "active" ? "default" : "secondary"}>
                      {session.status}
                    </Badge>
                    <DeleteSessionButton id={session.id} />
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}

      {(offset > 0 || offset + page.items.length < page.total) && (
        <div className="flex items-center justify-between">
          <Button asChild variant="outline" size="sm" disabled={offset === 0}>
            <Link href={`/sessions?offset=${Math.max(0, offset - PAGE_SIZE)}`}>Newer</Link>
          </Button>
          {offset + page.items.length < page.total && (
            <Button asChild variant="outline" size="sm">
              <Link href={`/sessions?offset=${offset + PAGE_SIZE}`}>Older</Link>
            </Button>
          )}
        </div>
      )}
    </Page>
  );
}
