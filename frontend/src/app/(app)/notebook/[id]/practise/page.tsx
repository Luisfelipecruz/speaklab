/**
 * Write it yourself: what you said, and a box to write it in English your own way.
 *
 * The versions you could have pasted are folded until you want them, so the English you
 * write is yours and not a copy. The check is the one a conversation gets — spelling from
 * a dictionary, then the grammar rules and the model's proposals inside the closed list
 * of mistake types — and the capture comes back on a schedule.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { Page, PageHeader } from "@/components/PageHeader";
import { TimeZoneCookie } from "@/components/TimeZoneCookie";
import { WriteItYourself } from "@/components/WriteItYourself";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Capture } from "@/lib/api";
import { excerpt, offered, VERSION_LABEL } from "@/lib/notebook";
import { serverRequestOrNull } from "@/lib/server-api";
import { readerZone } from "@/lib/server-zone";
import { dayOf, timeOf } from "@/lib/time";

export const dynamic = "force-dynamic";

export const metadata = { title: "Write it yourself — SpeakLab" };

export default async function PractisePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const captureId = Number(id);
  if (!Number.isInteger(captureId) || captureId <= 0) notFound();

  const [capture, zone] = await Promise.all([
    serverRequestOrNull<Capture>(`/captures/${captureId}`),
    readerZone(),
  ]);

  if (!capture) {
    return (
      <Page>
        <Alert className="w-fit max-w-2xl">
          <AlertDescription>
            That capture is not available. You may need to{" "}
            <Link href={`/login?next=/notebook/${captureId}/practise`} className="underline">
              sign in
            </Link>
            .
          </AlertDescription>
        </Alert>
      </Page>
    );
  }

  const where = [capture.app ? `In ${capture.app}` : null, `${dayOf(capture.created_at, zone)}, ${timeOf(capture.created_at, zone)}`]
    .filter(Boolean)
    .join(", ");
  const versions = offered(capture.mode).filter((version) => capture.versions[version]);

  return (
    <Page className="gap-6">
      <TimeZoneCookie />
      <Button asChild variant="ghost" size="sm" className="self-start">
        <Link href={`/notebook/${capture.id}`}>
          <ArrowLeft aria-hidden="true" />
          The moment
        </Link>
      </Button>
      <PageHeader title="Write it yourself" description={`${excerpt(capture.source_text)} — ${where}.`} />

      <div className="flex w-full max-w-3xl flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              You {capture.via === "voice" ? "said" : "wrote"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg leading-relaxed italic" data-testid="practise-source">
              «{capture.source_text}»
            </p>
          </CardContent>
        </Card>

        <WriteItYourself captureId={capture.id as number} zone={zone} />

        {versions.length > 0 && (
          <details className="rounded-lg border border-border p-4">
            <summary className="cursor-pointer text-sm font-medium">
              The {versions.length === 1 ? "version" : "two versions"} you could have pasted
            </summary>
            <dl className="mt-3 flex flex-col gap-3 text-sm">
              {versions.map((version) => (
                <div key={version}>
                  <dt className="font-medium">{VERSION_LABEL[version]}</dt>
                  <dd className="whitespace-pre-wrap text-muted-foreground">{capture.versions[version]}</dd>
                </div>
              ))}
            </dl>
          </details>
        )}

        <details className="text-sm text-muted-foreground">
          <summary className="cursor-pointer">How this is counted</summary>
          <p className="mt-2">
            A mistake counts when the dictionary finds a misspelling, or when the grammar
            rules or the language model propose it inside the closed list of mistake types,
            at or above the confidence floor speech uses. Written mistakes are kept apart
            from spoken ones, so writing never moves a figure about your speech. The
            comparison with the closer version is plain code, not the model.
          </p>
        </details>
      </div>
    </Page>
  );
}
