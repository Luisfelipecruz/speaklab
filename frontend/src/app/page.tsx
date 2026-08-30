import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { getHealth, PUBLIC_API_URL, type ServiceStatus } from "@/lib/api";

/**
 * The front door, and the stack describing itself.
 *
 * m1 built the second half: proof of something no unit test can give — that the browser
 * reaches the frontend container, the frontend container reaches the API container, and
 * the API container reaches Postgres. It renders whatever /health actually says,
 * including "degraded", which is the correct state on a machine where the model services
 * have not been started (I6, FR-27).
 *
 * m7 put a way in above it. Until this milestone the only entry point to the product was
 * a URL somebody had to know, which made "a person who is not the author can hold a
 * conversation without instructions" false on the first screen.
 */

export const dynamic = "force-dynamic";

/** What each model service is for, and which milestone builds it. */
const MODEL_SERVICES = [
  {
    name: "asr",
    milestone: "m4",
    role: "Transcript with word timestamps and per-word logprobs",
  },
  { name: "tts", milestone: "m5", role: "The persona's spoken reply" },
  {
    name: "pron",
    milestone: "m8",
    role: "Forced alignment and per-phoneme GOP",
  },
] as const;

function StatusBadge({ status }: { status: ServiceStatus | string }) {
  const variant =
    status === "ok" ? "default" : status === "error" ? "destructive" : "secondary";
  return <Badge variant={variant}>{status}</Badge>;
}

export default async function Home() {
  const health = await getHealth();

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-6 py-16">
      <header className="flex flex-col gap-4">
        <h1 className="text-4xl font-semibold tracking-tight">SpeakLab</h1>
        <p className="text-muted-foreground text-balance">
          Practise spoken English against local models. Scenario role-play, read-aloud
          pronunciation scoring with per-phoneme GOP, and progress you can actually
          measure.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Button asChild size="lg" className="h-11 px-6">
            <Link href="/scenarios">Start practising</Link>
          </Button>
          <Button asChild variant="ghost" size="lg" className="h-11 px-4">
            <Link href="/sessions">Your conversations</Link>
          </Button>
        </div>
        <p className="text-muted-foreground text-xs">
          You will need a microphone and about ten minutes. Nothing you say leaves this
          machine.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between gap-4">
            <span>Stack</span>
            {health ? (
              <StatusBadge status={health.status} />
            ) : (
              <Badge variant="destructive">api unreachable</Badge>
            )}
          </CardTitle>
          <CardDescription>
            Read from{" "}
            <code className="font-mono text-xs">{PUBLIC_API_URL}/health</code> on every
            request. A cached health check is not a health check.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          {health ? (
            <>
              <Row label="API" value={`v${health.version}`} status="ok" />
              <Separator />
              <Row
                label="Database"
                value={
                  health.database.latency_ms !== undefined
                    ? `SELECT 1 in ${health.database.latency_ms} ms`
                    : (health.database.detail ?? "no detail")
                }
                status={health.database.status}
              />
            </>
          ) : (
            <p className="text-muted-foreground">
              The API did not answer. Start it with{" "}
              <code className="font-mono text-xs">make up</code>, then reload.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Model services</CardTitle>
          <CardDescription>
            <code className="font-mono text-xs">asr</code> and{" "}
            <code className="font-mono text-xs">tts</code> are what a conversation needs;
            the stack still serves everything that is not speech while they are absent or
            still loading their weights (FR-27). Conversation also needs Ollama on the
            host — it is deliberately not a Compose service, because Docker on macOS
            cannot pass the GPU through.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          {MODEL_SERVICES.map(({ name, milestone, role }, index) => {
            const probe = health?.models?.[name];
            return (
              <div key={name} className="flex flex-col gap-3">
                {index > 0 ? <Separator /> : null}
                <div className="flex items-start justify-between gap-4">
                  <div className="flex flex-col gap-0.5">
                    <span className="font-mono font-medium">
                      {name}{" "}
                      <span className="text-muted-foreground font-sans text-xs">
                        · arrives in {milestone}
                      </span>
                    </span>
                    <span className="text-muted-foreground">{role}</span>
                  </div>
                  <StatusBadge status={probe?.status ?? "unknown"} />
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      <p className="text-muted-foreground text-xs">
        Milestone m7 — the conversation interface. Pronunciation scoring arrives in m8.
      </p>
    </main>
  );
}

function Row({
  label,
  value,
  status,
}: {
  label: string;
  value: string;
  status: ServiceStatus | string;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex flex-col gap-0.5">
        <span className="font-medium">{label}</span>
        <span className="text-muted-foreground">{value}</span>
      </div>
      <StatusBadge status={status} />
    </div>
  );
}
