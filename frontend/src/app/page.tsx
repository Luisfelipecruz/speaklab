import Link from "next/link";
import { GaugeIcon, MessagesSquareIcon, MicIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * The front door, for somebody who has not signed in.
 *
 * It used to be a service-status table: three container names, a database latency, and a
 * probe result for each model service. That is a page for whoever runs the stack, and it
 * was the first thing a learner saw. It now lives at /status, where the person who wants
 * it will look for it.
 *
 * What replaces it is the one thing a stranger needs — what this does, and the way in.
 * Somebody already signed in goes to /home instead; both buttons below lead there through
 * the ordinary redirect, so a returning visitor who bookmarked the root does not have to
 * find the entry point twice.
 *
 * No shell around it. The navigation rail is for people with practice to navigate.
 */

export const metadata = {
  title: "SpeakLab — practise spoken English against local models",
};

const CLAIMS = [
  {
    icon: MessagesSquareIcon,
    title: "Conversation with a goal",
    body: "A persona with a brief and something to push back about. You speak, it answers out loud, and the report at the end is counted from the turns rather than written about them.",
  },
  {
    icon: MicIcon,
    title: "Pronunciation, sound by sound",
    body: "Passages engineered to force one group of sounds. Forced alignment scores every phone against the one the text asked for, and says which sound came out instead.",
  },
  {
    icon: GaugeIcon,
    title: "Progress you can check",
    body: "Fluency, accuracy and breadth over weeks, each series gated on how much speech it rests on. Nothing plotted here is produced by a language model.",
  },
];

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col justify-center gap-12 px-6 py-16">
      <header className="flex max-w-2xl flex-col gap-5">
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">SpeakLab</h1>
        <p className="text-balance text-lg text-muted-foreground">
          Practise spoken English against models running on this machine. Scenario
          role-play, read-aloud pronunciation scoring with per-phoneme GOP, and progress
          you can actually measure.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Button asChild size="lg" className="h-11 px-6">
            <Link href="/home">Start practising</Link>
          </Button>
          <Button asChild variant="ghost" size="lg" className="h-11 px-4">
            <Link href="/login">Sign in</Link>
          </Button>
        </div>
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
