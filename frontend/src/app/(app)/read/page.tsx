/**
 * The passage catalogue.
 *
 * A server component for the same reason `/scenarios` is: `GET /passages` takes no
 * session, so there is nothing to forward and no reason to ship a fetch to the browser.
 *
 * **`phoneme_focus` is the filter that matters here**, and it is the difference between
 * this page and the scenario catalogue. A passage is not prose that happens to contain a
 * sound — it is engineered to force it repeatedly, which is why "the third street
 * theatre" contains *theatre, third, three, thousand, through, nothing, thin, thanked,
 * thought, throat, thumb, path, north, thirty, thistles, breath, truth, both, something,
 * thinking*. Somebody who knows /θ/ is their problem should be able to get to that
 * passage in one click, so the focus is a link rather than a label.
 */

import Link from "next/link";

import { Page, PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, CEFR_ORDER, type PassageSummary } from "@/lib/api";
import { serverRequest } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Read aloud — SpeakLab" };

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) search.set(key, value);
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export default async function ReadPage({
  searchParams,
}: {
  searchParams: Promise<{ band?: string; phoneme_focus?: string }>;
}) {
  const { band, phoneme_focus } = await searchParams;

  let passages: PassageSummary[] = [];
  let failure: string | null = null;
  try {
    passages = await serverRequest<PassageSummary[]>(
      `/passages${query({ band, phoneme_focus })}`,
    );
  } catch (error) {
    failure =
      error instanceof ApiError ? error.message : "The passage list could not be loaded.";
  }

  const focuses = [...new Set(passages.flatMap((one) => one.phoneme_focus))].sort();

  return (
    <Page>
      <PageHeader
        title="Read aloud"
        description="Each passage is built to make you produce one group of sounds over
          and over. Read it out, and every sound you make is scored against the sound the
          text asked for — including which sound came out instead."
      />

      {failure && (
        <Alert variant="destructive">
          <AlertDescription>{failure}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col gap-3">
        <FilterRow label="Level">
          <FilterLink href={`/read${query({ phoneme_focus })}`} active={!band}>
            any
          </FilterLink>
          {CEFR_ORDER.map((value) => (
            <FilterLink
              key={value}
              href={`/read${query({ band: value, phoneme_focus })}`}
              active={band === value}
            >
              {value}
            </FilterLink>
          ))}
        </FilterRow>

        {focuses.length > 1 && (
          <FilterRow label="Sound">
            <FilterLink href={`/read${query({ band })}`} active={!phoneme_focus}>
              any
            </FilterLink>
            {focuses.map((value) => (
              <FilterLink
                key={value}
                href={`/read${query({ band, phoneme_focus: value })}`}
                active={phoneme_focus === value}
              >
                {value}
              </FilterLink>
            ))}
          </FilterRow>
        )}
      </div>

      {!failure && passages.length === 0 ? (
        <Alert>
          <AlertDescription>
            No passages match that filter. If the list is empty everywhere, the seeds have
            not been loaded — run <code className="font-mono">make seed</code>.
          </AlertDescription>
        </Alert>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {passages.map((passage) => (
            <Card key={passage.slug} className="flex flex-col">
              <CardHeader className="gap-2">
                <CardTitle className="text-lg">
                  <Link href={`/read/${passage.slug}`} className="hover:underline">
                    {passage.title}
                  </Link>
                </CardTitle>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{passage.cefr_band}</Badge>
                  {passage.phoneme_focus.map((phone) => (
                    <Badge key={phone} variant="outline" className="font-mono">
                      {phone}
                    </Badge>
                  ))}
                </div>
              </CardHeader>
              <CardContent className="mt-auto text-sm text-muted-foreground">
                {passage.word_count} words
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </Page>
  );
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="w-14 text-xs text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

function FilterLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Badge asChild variant={active ? "default" : "outline"}>
      <Link href={href} aria-current={active ? "true" : undefined}>
        {children}
      </Link>
    </Badge>
  );
}
