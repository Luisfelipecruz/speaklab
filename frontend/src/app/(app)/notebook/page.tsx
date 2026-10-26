/**
 * The Notebook: every time you asked SpeakLab for English, or to check yours, kept so you
 * can write it yourself later.
 *
 * **The way in is on the page.** The desktop app opens its panel with fn; here the same
 * thing is a box, so the feature works in a browser and on a Mac without the key.
 *
 * **What is due comes first**, in a strip above the list: the captures written before and
 * due again. Below it, every capture by the day it was made, newest first, filtered by
 * where it is in the practice, by checks, or by the app it was for. Every figure on the
 * page is a count of stored rows.
 *
 * Server-rendered with the cookie forwarded, like every signed-in page, in the reader's
 * own time zone once their browser has named it.
 */

import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { CaptureCard } from "@/components/CaptureCard";
import { DeleteAllCaptures } from "@/components/DeleteCaptureButton";
import { Page, PageHeader } from "@/components/PageHeader";
import { SectionTabs } from "@/components/SectionTabs";
import { StatTile } from "@/components/StatTile";
import { TimeZoneCookie } from "@/components/TimeZoneCookie";
import { WriteInEnglish } from "@/components/WriteInEnglish";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CaptureList } from "@/lib/api";
import { byDay, excerpt } from "@/lib/notebook";
import { serverRequestOrNull } from "@/lib/server-api";
import { readerZone } from "@/lib/server-zone";

export const dynamic = "force-dynamic";

export const metadata = { title: "Notebook — SpeakLab" };

const PAGE = 20;

const VIEWS = [
  { key: "all", label: "All", query: {} },
  { key: "due", label: "Due again", query: { state: "due" } },
  { key: "to_practise", label: "To practise", query: { state: "to_practise" } },
  { key: "practised", label: "Practised", query: { state: "practised" } },
  { key: "check", label: "Checked", query: { mode: "check" } },
] as const;

interface Params {
  view?: string;
  app?: string;
  q?: string;
  offset?: string;
}

function href(params: Record<string, string | undefined>): string {
  const query = new URLSearchParams(
    Object.entries(params).filter((entry): entry is [string, string] => Boolean(entry[1])),
  ).toString();
  return query ? `/notebook?${query}` : "/notebook";
}

export default async function NotebookPage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const view = VIEWS.find((candidate) => candidate.key === params.view) ?? VIEWS[0];
  const offset = Math.max(0, Number(params.offset) || 0);
  const query = new URLSearchParams({
    ...view.query,
    ...(params.app ? { app: params.app } : {}),
    ...(params.q ? { q: params.q } : {}),
    limit: String(PAGE),
    offset: String(offset),
  });
  const filtered = view.key !== "all" || Boolean(params.app) || Boolean(params.q);

  const [list, due, zone] = await Promise.all([
    serverRequestOrNull<CaptureList>(`/captures?${query}`),
    filtered ? Promise.resolve(null) : serverRequestOrNull<CaptureList>("/captures?state=due&limit=3"),
    readerZone(),
  ]);

  if (!list) {
    return (
      <Page>
        <Alert className="w-fit max-w-2xl">
          <AlertDescription>
            <Link href="/login?next=/notebook" className="underline">
              Sign in
            </Link>{" "}
            to see your Notebook.
          </AlertDescription>
        </Alert>
      </Page>
    );
  }

  const { counts } = list;
  const days = byDay(list.items, zone);
  const keep = { app: params.app, q: params.q };

  return (
    <Page className="gap-6">
      <TimeZoneCookie />
      <PageHeader
        title="Notebook"
        description="What you asked SpeakLab to say in English, or to check. Write each one yourself when you have a minute; what is due again comes first."
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="captures this week" value={counts.this_week} />
        <StatTile label="written yourself this week" value={counts.practised_this_week} />
        <StatTile label="with no counted mistake" value={counts.clean_this_week} />
        <StatTile label="due again" value={counts.due} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Say it in English</CardTitle>
        </CardHeader>
        <CardContent>
          <WriteInEnglish />
        </CardContent>
      </Card>

      {due && due.items.length > 0 && (
        <section
          aria-label="Due again"
          className="flex flex-col gap-3 rounded-xl border border-primary/30 bg-primary/5 p-4"
        >
          <h2 className="text-sm font-semibold">
            {counts.due} due again — write {counts.due === 1 ? "it" : "them"} yourself
          </h2>
          <ul className="flex flex-col gap-2">
            {due.items.map((item) => (
              <li key={item.id}>
                <Link
                  href={`/notebook/${item.id}/practise`}
                  className="group flex items-center gap-2 text-sm hover:text-primary"
                >
                  <span className="flex-1 truncate">«{excerpt(item.source_text, 12)}»</span>
                  <ArrowRight className="size-4 shrink-0" aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="flex flex-col gap-3">
        <SectionTabs
          label="Which captures"
          sections={VIEWS.map((candidate) => ({
            key: candidate.key,
            label: candidate.label,
            href: href({ view: candidate.key === "all" ? undefined : candidate.key, ...keep }),
          }))}
          current={view.key}
        />
        <div className="flex flex-wrap items-center gap-2">
          {list.apps.map((app) => (
            <Button key={app} asChild size="sm" variant={params.app === app ? "default" : "outline"}>
              <Link
                href={href({
                  view: view.key === "all" ? undefined : view.key,
                  app: params.app === app ? undefined : app,
                  q: params.q,
                })}
                aria-pressed={params.app === app}
              >
                {app}
              </Link>
            </Button>
          ))}
          <form action="/notebook" className="ml-auto flex items-center gap-2">
            {view.key !== "all" && <input type="hidden" name="view" value={view.key} />}
            {params.app && <input type="hidden" name="app" value={params.app} />}
            <label htmlFor="notebook-q" className="sr-only">
              Look for words
            </label>
            <input
              id="notebook-q"
              name="q"
              defaultValue={params.q ?? ""}
              placeholder="Look for words"
              className="h-8 rounded-md border border-input bg-transparent px-2 text-sm"
            />
          </form>
        </div>
      </div>

      {days.length === 0 ? (
        <Card className="max-w-2xl">
          <CardContent className="flex flex-col gap-2 py-2 text-sm text-muted-foreground">
            {filtered ? (
              <p>Nothing here matches. <Link href="/notebook" className="underline">Show everything</Link>.</p>
            ) : (
              <p>
                Nothing yet. In the SpeakLab app, hold fn in any app and say it in your
                language, or use the box above; each one is kept here to write yourself later.
              </p>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col gap-6">
          {days.map((day) => (
            <section key={day.key} aria-label={day.label} className="flex flex-col gap-3">
              <h2 className="text-sm font-semibold text-muted-foreground">{day.label}</h2>
              {day.items.map((item) => (
                <CaptureCard key={item.id} item={item} zone={zone} />
              ))}
            </section>
          ))}
        </div>
      )}

      {(offset > 0 || offset + list.items.length < list.matching) && (
        <nav aria-label="More captures" className="flex items-center gap-3 text-sm">
          {offset > 0 && (
            <Link href={href({ view: params.view, ...keep, offset: String(Math.max(0, offset - PAGE)) })} className="underline">
              Newer
            </Link>
          )}
          {offset + list.items.length < list.matching && (
            <Link href={href({ view: params.view, ...keep, offset: String(offset + PAGE) })} className="underline">
              Older
            </Link>
          )}
          <span className="text-muted-foreground">
            {offset + 1}–{offset + list.items.length} of {list.matching}
          </span>
        </nav>
      )}

      <footer className="flex flex-col items-start gap-3 border-t border-border pt-4 text-xs text-muted-foreground">
        <p>
          Only the text is kept, never the recording, with the app it was for and the time.
          SpeakLab never reads your screen.
        </p>
        <DeleteAllCaptures count={counts.total} />
      </footer>
    </Page>
  );
}
