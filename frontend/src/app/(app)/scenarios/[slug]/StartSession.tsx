"use client";

/**
 * The one interactive part of a scenario page.
 *
 * Starting a session is a POST that needs the browser's session cookie, and it generates
 * the persona's opening line before it answers — a model call, a second or more — so the
 * button has a real pending state rather than an optimistic navigation.
 *
 * **The two failures it can hit are different and are said differently.** A 401 means
 * nobody is signed in, which is not an error but a missing step, so it sends the person
 * to the login page carrying where they were going. A 503 means Ollama is not answering,
 * and `POST /sessions` writes nothing when that happens — no empty session is left in
 * the history — so the honest message is that nothing was started and it is worth
 * retrying.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError, startSession } from "@/lib/api";

export function StartSession({ slug, title }: { slug: string; title: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setError(null);
    setPending(true);
    try {
      const session = await startSession(slug);
      router.push(`/sessions/${session.id}`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        router.push(`/login?next=${encodeURIComponent(`/scenarios/${slug}`)}`);
        return;
      }
      setError(
        cause instanceof ApiError
          ? cause.status === 503
            ? `${cause.message} Nothing was started, so you can try again.`
            : cause.message
          : "The conversation could not be started.",
      );
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Button size="lg" className="h-11 w-fit px-6" onClick={start} disabled={pending}>
        {pending ? `Starting “${title}”…` : "Start the conversation"}
      </Button>

      <p className="text-xs text-muted-foreground">
        The persona speaks first. You will need to allow microphone access — everything
        stays on this machine.
      </p>
    </div>
  );
}
