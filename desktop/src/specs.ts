// The units the supervisor runs, which is docker-compose.yml's graph with the containers
// replaced by processes: the database first, then the schema and the seeded material, then
// the API; the three model services at once, waiting for nothing.

import { rmSync } from "node:fs";

import { DB_NAME, DB_USER, HOST, PORTS, postgresEnv, serviceEnv, type Secrets, type Settings } from "./environment.ts";
import type { Paths, Service } from "./layout.ts";
import { type Command, launch as launchProcess, runOnce } from "./processes.ts";
import { writePasswordFile } from "./data.ts";
import type { Handle, Spec } from "./supervisor.ts";

export interface Context {
  p: Paths;
  base: Record<string, string>;
  secrets: Secrets;
  settings: Settings;
  /** No cluster yet: initdb and createdb run before anything else. */
  firstLaunch: boolean;
}

type Launch = (name: string, command: Command) => Handle;

/** A newer app's migration, which this app does not know, is the one failure named here. */
export function explainMigration(tail: string): string | undefined {
  if (/Can't locate revision identified by/.test(tail)) {
    return "This data was written by a newer SpeakLab. Install the newer version; this one will not run against a database it does not know.";
  }
  return undefined;
}

async function healthy(port: number, check: (body: Record<string, unknown>) => boolean): Promise<boolean> {
  try {
    const response = await fetch(`http://${HOST}:${port}/health`, { signal: AbortSignal.timeout(2000) });
    if (response.status !== 200) return false;
    return check((await response.json()) as Record<string, unknown>);
  } catch {
    return false;
  }
}

const READY: Record<Service, (body: Record<string, unknown>) => boolean> = {
  api: (body) => (body.database as { status?: string } | undefined)?.status === "ok",
  asr: (body) => body.model_loaded === true,
  tts: (body) => body.voice_loaded === true,
  pron: (body) => body.model_loaded === true,
};

export function buildSpecs(ctx: Context, launch?: Launch): Spec[] {
  const { p, base, secrets, settings } = ctx;
  const start: Launch = launch ?? ((name, command) => launchProcess(name, command, p.logs, p.run));
  const pgEnv = postgresEnv(base);
  const pgClient = { ...pgEnv, PGPASSWORD: secrets.dbPassword };
  const apiEnv = serviceEnv("api", base, p, secrets, settings);
  const python = (service: Service, args: string[]): Command => ({
    file: p.python,
    args,
    cwd: p.source(service),
    env: service === "api" ? apiEnv : serviceEnv(service, base, p, secrets, settings),
  });
  const uvicorn = (service: Service, module: string): Command =>
    python(service, ["-m", "uvicorn", `${module}:app`, "--host", HOST, "--port", String(PORTS[service])]);

  const specs: Spec[] = [];
  if (ctx.firstLaunch) {
    specs.push({
      name: "initdb",
      kind: "job",
      needs: [],
      launch: () => {
        const pwfile = writePasswordFile(p, secrets);
        const handle = start("initdb", {
          file: p.pg("initdb"),
          args: [
            "-D", p.cluster, "-U", DB_USER, `--pwfile=${pwfile}`, "-E", "UTF8",
            "--locale=en_US.UTF-8", "--locale-provider=libc",
            "--auth-host=scram-sha-256", "--auth-local=scram-sha-256",
          ],
          cwd: p.run,
          env: pgEnv,
        });
        void handle.exited.then(() => rmSync(pwfile, { force: true }));
        return handle;
      },
    });
  }
  specs.push({
    name: "postgres",
    kind: "service",
    needs: ctx.firstLaunch ? ["initdb"] : [],
    // TCP on 127.0.0.1 only, and no Unix socket: every client connects by address, and a
    // socket under Application Support could pass macOS's 104-byte limit on a long name.
    launch: () =>
      start("postgres", {
        file: p.pg("postgres"),
        args: ["-D", p.cluster, "-p", String(PORTS.postgres), "-c", `listen_addresses=${HOST}`, "-c", "unix_socket_directories="],
        cwd: p.run,
        env: pgEnv,
      }),
    ready: async () =>
      (
        await runOnce({
          file: p.pg("pg_isready"),
          args: ["-h", HOST, "-p", String(PORTS.postgres), "-U", DB_USER, "-d", "postgres", "-q"],
          cwd: p.run,
          env: pgClient,
        })
      ).code === 0,
    stopSignal: "SIGINT",
    stopTimeoutMs: 30_000,
  });
  if (ctx.firstLaunch) {
    specs.push({
      name: "createdb",
      kind: "job",
      needs: ["postgres"],
      launch: () =>
        start("createdb", {
          file: p.pg("createdb"),
          args: ["-h", HOST, "-p", String(PORTS.postgres), "-U", DB_USER, DB_NAME],
          cwd: p.run,
          env: pgClient,
        }),
    });
  }
  specs.push(
    {
      name: "migrate",
      kind: "job",
      needs: [ctx.firstLaunch ? "createdb" : "postgres"],
      launch: () => start("migrate", python("api", ["-m", "alembic", "upgrade", "head"])),
      explain: explainMigration,
    },
    { name: "seed", kind: "job", needs: ["migrate"], launch: () => start("seed", python("api", ["-m", "scripts.seed"])) },
    {
      name: "api",
      kind: "service",
      needs: ["seed"],
      launch: () => start("api", uvicorn("api", "main")),
      ready: () => healthy(PORTS.api, READY.api),
    },
  );
  for (const service of ["asr", "tts", "pron"] as const) {
    specs.push({
      name: service,
      kind: "service",
      needs: [],
      launch: () => start(service, uvicorn(service, "app")),
      ready: () => healthy(PORTS[service], READY[service]),
    });
  }
  return specs;
}
