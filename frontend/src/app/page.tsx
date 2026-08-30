import { Badge } from "@/components/ui/badge";
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
 * The m1 page: the stack, describing itself.
 *
 * It exists to prove one thing that no unit test can — that the browser reaches the
 * frontend container, the frontend container reaches the API container, and the API
 * container reaches Postgres. It renders whatever /health actually says, including
 * "degraded", because degraded is the correct and expected state of this repository
 * until m4 builds the first model service.
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
      <header className="flex flex-col gap-2">
        <h1 className="text-4xl font-semibold tracking-tight">SpeakLab</h1>
        <p className="text-muted-foreground text-balance">
          Practise spoken English against local models. Scenario role-play, read-aloud
          pronunciation scoring with per-phoneme GOP, and progress you can actually
          measure.
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
            None of these are running yet, and the stack is designed to work without
            them. The API serves everything that is not speech while they are absent or
            still loading their weights.
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
        Milestone m1 — scaffold, Compose, Postgres. The conversation loop arrives in m6.
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
