/**
 * The moment of one capture, as SpeakLab kept it: where and when, what was said, the
 * English used and the one not used, what the keep check kept, the phrases worth keeping,
 * and what has been practised since — then the ways to practise it.
 *
 * **It never shows more than was kept.** The moment is the app in front, the time and the
 * words. SpeakLab does not read the window, the e-mail being written or anything else on
 * the screen, and the page says so where a reader would wonder.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, MessagesSquare, PenLine } from "lucide-react";

import { CaptureEnglish } from "@/components/CaptureEnglish";
import { CaptureFixes } from "@/components/CaptureFixes";
import { CopyButton } from "@/components/CopyButton";
import { DeleteCaptureButton } from "@/components/DeleteCaptureButton";
import { OtherVersion } from "@/components/OtherVersion";
import { Page, PageHeader } from "@/components/PageHeader";
import { SayItYourself } from "@/components/SayItYourself";
import { TimeZoneCookie } from "@/components/TimeZoneCookie";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Capture } from "@/lib/api";
import {
  comesBack,
  excerpt,
  howLabel,
  keptEverywhere,
  otherVersion,
  VERSION_LABEL,
} from "@/lib/notebook";
import { serverRequestOrNull } from "@/lib/server-api";
import { readerZone } from "@/lib/server-zone";
import { dayOf, timeOf } from "@/lib/time";

export const dynamic = "force-dynamic";

export const metadata = { title: "The moment — SpeakLab" };

export default async function MomentPage({ params }: { params: Promise<{ id: string }> }) {
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
            That capture is not available. It may have been deleted, belong to another
            account, or you may need to{" "}
            <Link href={`/login?next=/notebook/${captureId}`} className="underline">
              sign in
            </Link>
            .
          </AlertDescription>
        </Alert>
      </Page>
    );
  }

  const kept = keptEverywhere(capture);
  const other = otherVersion(capture);
  const said = capture.via === "voice";
  const seconds = capture.duration_ms ? Math.round(capture.duration_ms / 1000) : null;

  return (
    <Page className="gap-6">
      <TimeZoneCookie />
      <Button asChild variant="ghost" size="sm" className="self-start">
        <Link href="/notebook">
          <ArrowLeft aria-hidden="true" />
          Notebook
        </Link>
      </Button>
      <PageHeader
        eyebrow={
          <div className="flex flex-wrap gap-2">
            {capture.app && <Badge variant="outline">{capture.app}</Badge>}
            <Badge variant="outline">
              {howLabel(capture)}
              {seconds ? `, ${seconds} s` : ""}
            </Badge>
            <Badge variant="secondary">You copied {VERSION_LABEL[capture.chosen]}</Badge>
          </div>
        }
        title={excerpt(capture.source_text)}
        description={`${dayOf(capture.created_at, zone)}, ${timeOf(capture.created_at, zone)}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button asChild>
              <Link href={`/notebook/${capture.id}/practise`}>
                <PenLine aria-hidden="true" />
                Write it yourself
              </Link>
            </Button>
            <DeleteCaptureButton id={capture.id as number} back />
          </div>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                What you {said ? "said" : "wrote"}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {capture.mode === "check" ? (
                <CaptureFixes
                  text={capture.source_text}
                  fixes={capture.fixes}
                  uncounted={said ? "shown, not counted: said aloud" : undefined}
                />
              ) : (
                <p className="text-base leading-relaxed italic">«{capture.source_text}»</p>
              )}
              {kept.length > 0 && (
                <p className="text-sm text-muted-foreground" data-testid="kept">
                  Kept in every version: {kept.join(" · ")}
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex flex-col gap-4">
              <CaptureEnglish
                capture={capture}
                version={capture.chosen}
                heading={`The English you used · ${VERSION_LABEL[capture.chosen]}`}
                actions={<CopyButton text={capture.text} />}
              />
              <OtherVersion capture={capture} version={other} />
              {capture.notes.map((note) => (
                <p key={note} className="text-sm text-muted-foreground">
                  {note}
                </p>
              ))}
            </CardContent>
          </Card>

          {capture.phrases.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Phrases worth keeping</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="pb-2 font-medium">You said</th>
                      <th className="pb-2 font-medium">In English</th>
                      <th className="pb-2 text-right font-medium">In your other captures</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {capture.phrases.map((phrase) => (
                      <tr key={phrase.source}>
                        <td className="py-2 pr-3 italic">{phrase.source}</td>
                        <td className="py-2 pr-3 font-medium">{phrase.english}</td>
                        <td className="py-2 text-right tabular-nums">{phrase.elsewhere}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-xs text-muted-foreground">
                  The language model picks the phrases; each is kept only when both halves
                  are found word for word where they are quoted from. The last column is
                  plain code: the same English in your other captures, so the phrases you
                  keep needing stand out.
                </p>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Since then</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              {capture.attempts.length === 0 ? (
                <p className="text-muted-foreground">Not written yourself yet.</p>
              ) : (
                <ol className="flex flex-col gap-2" aria-label="Written yourself">
                  {capture.attempts.map((attempt) => (
                    <li key={attempt.id} className="flex flex-wrap gap-x-2">
                      <span className="font-medium tabular-nums">
                        {dayOf(attempt.created_at, zone)}, {timeOf(attempt.created_at, zone)}
                      </span>
                      <span className="text-muted-foreground">
                        {attempt.counted === 0
                          ? `no counted mistake in ${attempt.word_count} words`
                          : `${attempt.counted} counted mistake${attempt.counted === 1 ? "" : "s"} in ${attempt.word_count} words`}
                        , box {attempt.box}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
              {capture.due_at && (
                <p data-testid="due">
                  Comes back <strong>{comesBack(capture.due_at, zone)}</strong>.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Say it yourself</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <p className="text-sm text-muted-foreground">
                Say the English you used, and see what the recogniser heard against it.
                Nothing is stored.
              </p>
              <SayItYourself captureId={capture.id as number} />
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex flex-col gap-2 text-sm">
              <Button variant="outline" disabled className="self-start">
                <MessagesSquare aria-hidden="true" />
                Practise it as a conversation
              </Button>
              <p className="text-muted-foreground">
                Later: someone in the scene asks you about it, and you answer in English.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        The moment is what SpeakLab can know without reading your screen: the app in front,
        the time and your words. It never reads the window, the message you were writing or
        anything else on screen.
      </p>
    </Page>
  );
}
