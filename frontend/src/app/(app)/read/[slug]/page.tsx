/**
 * One passage, ready to read.
 *
 * Server-rendered then hydrated, the same arrangement `/sessions/[id]` uses: the passage
 * text is public and static, so it arrives in the HTML and is readable before any
 * JavaScript runs — which matters more here than anywhere else in the app, because the
 * text is the thing the user is about to perform. `PassageReader` takes over for the
 * microphone.
 */

import { notFound } from "next/navigation";

import { Page, PageHeader } from "@/components/PageHeader";
import { PassageReader } from "@/components/PassageReader";
import { Badge } from "@/components/ui/badge";
import { ApiError, type PassageDetail } from "@/lib/api";
import { serverRequest } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export default async function PassagePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  let passage: PassageDetail;
  try {
    passage = await serverRequest<PassageDetail>(`/passages/${slug}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  return (
    <Page>
      <PageHeader
        eyebrow={
          <>
            <Badge variant="secondary">{passage.cefr_band}</Badge>
            {passage.phoneme_focus.map((phone) => (
              <Badge key={phone} variant="outline" className="font-mono">
                {phone}
              </Badge>
            ))}
            <span className="text-xs text-muted-foreground">{passage.word_count} words</span>
          </>
        }
        title={passage.title}
      />

      <PassageReader passage={passage} />
    </Page>
  );
}
