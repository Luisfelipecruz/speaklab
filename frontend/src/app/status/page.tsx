/**
 * The stack describing itself, for whoever is running it.
 *
 * This is proof of something no unit test can give — that the browser reaches the
 * frontend container, the frontend container reaches the API container, and the API
 * container reaches Postgres. It renders whatever /health actually says, including
 * "degraded", which is the correct state on a machine where the model services have not
 * been started.
 *
 * **It is not in the navigation, and that is the point of it being here.** It used to be
 * the content of the front page, where it was the first thing a learner saw: three
 * container names and a database latency, none of which is about them. It is reachable
 * by typing the address, which is what the person who needs it will do.
 */

import Link from "next/link";

import { Page, PageHeader } from "@/components/PageHeader";
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

export const dynamic = "force-dynamic";

export const metadata = { title: "Status — SpeakLab" };

/** What each model service is for. */
const MODEL_SERVICES = [
  {
    name: "asr",
    role: "Transcript with word timestamps and per-word logprobs",
  },
  { name: "tts", role: "The persona's spoken reply" },
  {
    name: "pron",
    role: "Forced alignment and per-phoneme GOP",
  },
] as const;

function StatusBadge({ status }: { status: ServiceStatus | string }) {
  const variant =
    status === "ok" ? "default" : status === "error" ? "destructive" : "secondary";
  return <Badge variant={variant}>{status}</Badge>;
}

export default async function StatusPage() {
  const health = await getHealth();

  return (
    <main className="px-4 py-10 sm:px-6">
      <Page>
        <PageHeader
          title="Status"
          description="Read live on every request. A cached health check is not a health check."
          actions={
            <Button asChild variant="outline" size="sm">
              <Link href="/home">Back to practice</Link>
            </Button>
          }
        />

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
              From <code className="font-mono text-xs">{PUBLIC_API_URL}/health</code>.
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
              still loading their weights. Conversation also needs Ollama on the host — it
              is deliberately not a Compose service, because Docker on macOS cannot pass
              the GPU through.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            {MODEL_SERVICES.map(({ name, role }, index) => {
              const probe = health?.models?.[name];
              return (
                <div key={name} className="flex flex-col gap-3">
                  {index > 0 ? <Separator /> : null}
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex flex-col gap-0.5">
                      <span className="font-mono font-medium">{name}</span>
                      <span className="text-muted-foreground">{role}</span>
                    </div>
                    <StatusBadge status={probe?.status ?? "unknown"} />
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      </Page>
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
