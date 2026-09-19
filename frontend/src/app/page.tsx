import Image from "next/image";
import Link from "next/link";
import { GaugeIcon, MessagesSquareIcon, MicIcon } from "lucide-react";

import talk from "@/assets/talk.png";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * The front door, for somebody who has not signed in.
 *
 * It shows the product before it describes it: one sentence, the conversation screen as
 * it looks mid-reply, and the names of the models that make it work. A first screen made
 * of paragraphs asks a stranger to imagine the thing; a picture of the thing does not.
 * The three cards under the picture say what is counted, and they come second.
 *
 * The screen is a photograph of the running stack, retaken whenever the conversation page
 * changes, and it is served as the file it is — the page shows it at one size, and an
 * optimiser between the file and the page would add a moving part for nothing.
 *
 * Somebody already signed in goes to /home instead; both buttons lead there through the
 * ordinary redirect, so a returning visitor who bookmarked the root does not have to
 * find the entry point twice. The service page is for whoever runs the stack, and it
 * lives at /status.
 *
 * No shell around it. The navigation rail is for people with practice to navigate.
 */

export const metadata = {
  title: "SpeakLab — practise spoken English against local models",
};

/** What does each part of a turn, in the order a turn passes through them. */
const STACK = [
  { part: "Whisper", does: "hears you" },
  { part: "Gemma 4", does: "answers in character" },
  { part: "Piper", does: "says the reply" },
  { part: "wav2vec2", does: "scores your sounds" },
  { part: "your machine", does: "runs all of it" },
];

const CLAIMS = [
  {
    icon: MessagesSquareIcon,
    title: "Conversation with a goal",
    body: "A persona with a brief and something to push back about. You speak, it answers out loud, and the report at the end is counted from the turns rather than written about them.",
  },
  {
    icon: MicIcon,
    title: "Pronunciation, sound by sound",
    body: "Passages built to bring out one group of sounds. Every sound you make is scored against the one the text asked for, and the report says which sound came out instead.",
  },
  {
    icon: GaugeIcon,
    title: "Progress you can check",
    body: "Fluency, accuracy and breadth over weeks, each series shown only once it rests on enough speech. Nothing plotted here is produced by a language model.",
  },
];

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-12 px-6 py-12 sm:py-16">
      <header className="flex flex-col gap-6">
        <div className="flex max-w-2xl flex-col gap-4">
          <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">SpeakLab</h1>
          <p className="text-balance text-lg text-muted-foreground">
            Talk your way through a scenario with a persona that answers out loud, and read
            a report that is counted from what you said — on models running on this
            machine.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Button asChild size="lg" className="h-11 px-6">
              <Link href="/home">Start practising</Link>
            </Button>
            <Button asChild variant="ghost" size="lg" className="h-11 px-4">
              <Link href="/login">Sign in</Link>
            </Button>
          </div>
        </div>

        <figure className="flex flex-col gap-3">
          <Image
            src={talk}
            alt="A conversation in SpeakLab: the persona's reply beside the learner's turn, the time the turn took to be heard, thought about and spoken, and the Hold to speak button."
            priority
            unoptimized
            sizes="(min-width: 1024px) 960px, 100vw"
            className="w-full rounded-xl border border-border shadow-sm"
          />
          <figcaption className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {STACK.map(({ part, does }) => (
              <Badge key={part} variant="outline" className="gap-1 font-normal">
                <span className="font-medium text-foreground">{part}</span> {does}
              </Badge>
            ))}
          </figcaption>
        </figure>

        <p className="text-xs text-muted-foreground">
          You will need a microphone and about ten minutes. Nothing you say leaves this
          machine.
        </p>
      </header>

      <div className="grid gap-4 md:grid-cols-3">
        {CLAIMS.map(({ icon: Icon, title, body }) => (
          <Card key={title}>
            <CardHeader className="gap-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Icon className="size-4" />
                {title}
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">{body}</CardContent>
          </Card>
        ))}
      </div>

      <p className="text-xs text-muted-foreground">
        Running the stack yourself?{" "}
        <Link href="/status" className="underline">
          Service status
        </Link>
        .
      </p>
    </main>
  );
}
