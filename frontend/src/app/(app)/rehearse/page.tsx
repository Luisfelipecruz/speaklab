/**
 * Your scripts: the talks you have pasted, and how much of each you have rehearsed.
 *
 * The one worked on most recently is first, because the thing somebody opens this page to
 * do is carry on with the talk they are giving on Thursday.
 *
 * Server-rendered with the cookie forwarded, like every signed-in page.
 */

import Link from "next/link";
import { Plus } from "lucide-react";

import { Page, PageHeader } from "@/components/PageHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PresentationList } from "@/lib/api";
import { serverRequestOrNull } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Rehearse — SpeakLab" };

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

export default async function RehearsePage() {
  const listing = await serverRequestOrNull<PresentationList>("/presentations");

  if (!listing) {
    return (
      <Page>
        <Alert className="w-fit max-w-2xl">
          <AlertDescription>
            <Link href="/login?next=/rehearse" className="underline">
              Sign in
            </Link>{" "}
            to rehearse a script of your own.
          </AlertDescription>
        </Alert>
      </Page>
    );
  }

  return (
    <Page className="gap-8">
      <PageHeader
        title="Rehearse"
        description="Paste the script of a talk. It is split into sections you can say as often as
          you like, and every take is compared with what you wrote, timed and counted."
        actions={
          <Button asChild>
            <Link href="/rehearse/new">
              <Plus aria-hidden="true" />
              New script
            </Link>
          </Button>
        }
      />

      {listing.items.length === 0 ? (
        <p className="max-w-2xl text-sm text-muted-foreground">
          Nothing here yet. Paste a talk — a conference session, a stand-up, a demo — and it
          is split into sections of about a paragraph each.
        </p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {listing.items.map((item) => (
            <li key={item.id}>
              <Link href={`/rehearse/${item.id}`} className="group block h-full">
                <Card className="h-full transition-colors group-hover:border-primary">
                  <CardHeader>
                    <CardTitle className="text-base group-hover:text-primary">
                      {item.title}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground tabular-nums">
                    {plural(item.sections, "section", "sections")} ·{" "}
                    {plural(item.takes, "take", "takes")} ·{" "}
                    {plural(item.word_count, "word", "words")}
                  </CardContent>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Page>
  );
}
