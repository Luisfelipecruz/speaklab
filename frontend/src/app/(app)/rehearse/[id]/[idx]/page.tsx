/**
 * One section: the words, the recorder, and every take of it so far.
 *
 * Server-rendered with the cookie forwarded; the recorder and the takes are the one
 * client component, because a take is scored while the page is open and the page has to
 * follow it.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { SectionRehearsal } from "@/app/(app)/rehearse/[id]/[idx]/SectionRehearsal";
import { Page, PageHeader } from "@/components/PageHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { PresentationPage, Take } from "@/lib/api";
import { serverRequestOrNull } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Rehearse — SpeakLab" };

export default async function SectionPage({
  params,
}: {
  params: Promise<{ id: string; idx: string }>;
}) {
  const { id, idx } = await params;
  if (!/^\d+$/.test(id) || !/^\d+$/.test(idx)) notFound();

  const [page, takes] = await Promise.all([
    serverRequestOrNull<PresentationPage>(`/presentations/${id}`),
    serverRequestOrNull<{ items: Take[] }>(`/presentations/${id}/sections/${idx}/takes`),
  ]);

  const section = page?.presentation.sections.find((item) => item.idx === Number(idx));

  if (!page || !section) {
    return (
      <Page>
        <Alert className="w-fit max-w-2xl">
          <AlertDescription>
            That section is not available. You may need to{" "}
            <Link href={`/login?next=/rehearse/${id}/${idx}`} className="underline">
              sign in
            </Link>
            .
          </AlertDescription>
        </Alert>
      </Page>
    );
  }

  return (
    <Page className="gap-6">
      <PageHeader
        eyebrow={
          <Button asChild variant="ghost" size="sm" className="-ml-2">
            <Link href={`/rehearse/${id}`}>
              <ArrowLeft aria-hidden="true" />
              {page.presentation.title}
            </Link>
          </Button>
        }
        title={`Section ${section.idx + 1} of ${page.presentation.sections.length}`}
        description={`${section.word_count} words.`}
      />

      <SectionRehearsal
        presentationId={page.presentation.id}
        section={section}
        earlier={takes?.items ?? []}
      />
    </Page>
  );
}
