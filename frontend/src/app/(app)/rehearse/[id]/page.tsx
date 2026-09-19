/**
 * One script: its sections, how each has gone, and what to rehearse next.
 *
 * The sections are a list rather than a grid, because they are a talk and a talk has an
 * order. Each row carries the first words — enough to recognise it without reading it —
 * the count of takes, and how the last one went.
 *
 * Server-rendered with the cookie forwarded; the delete button is the one client piece.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { DeletePresentationButton } from "@/app/(app)/rehearse/[id]/DeletePresentationButton";
import { Page, PageHeader } from "@/components/PageHeader";
import { RehearseNext } from "@/components/RehearseNext";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { PresentationPage } from "@/lib/api";
import { clock } from "@/lib/answers";
import { serverRequestOrNull } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Rehearse — SpeakLab" };

function opening(body: string): string {
  const words = body.split(/\s+/);
  return words.length <= 12 ? body : `${words.slice(0, 12).join(" ")}…`;
}

export default async function PresentationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();

  const page = await serverRequestOrNull<PresentationPage>(`/presentations/${id}`);

  if (!page) {
    return (
      <Page>
        <Alert className="w-fit max-w-2xl">
          <AlertDescription>
            That script is not available. You may need to{" "}
            <Link href={`/login?next=/rehearse/${id}`} className="underline">
              sign in
            </Link>
            .
          </AlertDescription>
        </Alert>
      </Page>
    );
  }

  const { presentation } = page;
  const sectionIndexById = new Map(
    presentation.sections.map((section) => [section.id, section.idx]),
  );

  return (
    <Page className="gap-6">
      <PageHeader
        eyebrow={
          <Button asChild variant="ghost" size="sm" className="-ml-2">
            <Link href="/rehearse">
              <ArrowLeft aria-hidden="true" />
              All scripts
            </Link>
          </Button>
        }
        title={presentation.title}
        description={`${presentation.word_count} words in ${presentation.sections.length} ${
          presentation.sections.length === 1 ? "section" : "sections"
        }.`}
        actions={
          <DeletePresentationButton id={presentation.id} title={presentation.title} />
        }
      />

      <RehearseNext
        items={page.next_up}
        presentationId={presentation.id}
        sectionIndexById={sectionIndexById}
        caveat={page.caveat}
      />

      <section className="flex flex-col gap-3" aria-labelledby="sections">
        <h2 id="sections" className="text-lg font-semibold tracking-tight">
          The sections
        </h2>
        <ul className="flex flex-col divide-y divide-border rounded-xl border">
          {presentation.sections.map((section) => (
            <li
              key={section.id}
              className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 px-5 py-4"
            >
              <div className="flex min-w-0 flex-col gap-1">
                <span className="flex items-center gap-2 text-xs text-muted-foreground tabular-nums">
                  <span>Section {section.idx + 1}</span>
                  <span>·</span>
                  <span>{section.word_count} words</span>
                  {section.target_seconds !== null && (
                    <>
                      <span>·</span>
                      <span>target {clock(section.target_seconds * 1000)}</span>
                    </>
                  )}
                  {!section.scorable && (
                    <Badge variant="secondary">no sound scores</Badge>
                  )}
                </span>
                <span className="truncate text-sm">{opening(section.body)}</span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {section.takes === 0
                    ? "No takes yet"
                    : `${section.takes} ${section.takes === 1 ? "take" : "takes"}${
                        section.latest
                          ? ` · last one missed or changed ${section.latest.missed} of ${section.word_count} words`
                          : ""
                      }`}
                </span>
              </div>
              <Button asChild variant="outline" size="sm">
                <Link href={`/rehearse/${presentation.id}/${section.idx}`}>Rehearse</Link>
              </Button>
            </li>
          ))}
        </ul>
      </section>
    </Page>
  );
}
