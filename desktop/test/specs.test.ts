import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, it } from "node:test";

import { baseEnv } from "../src/environment.ts";
import { paths } from "../src/layout.ts";
import type { Command } from "../src/processes.ts";
import { buildSpecs, explainMigration } from "../src/specs.ts";
import type { Exit, Handle } from "../src/supervisor.ts";

const data = mkdtempSync(join(tmpdir(), "speaklab-specs-"));
after(() => rmSync(data, { recursive: true, force: true }));
const p = paths({ resources: "/R", data });
const secrets = { dbPassword: "pw-123", jwtSecret: "f".repeat(64) };

function context(firstLaunch: boolean) {
  return { p, base: baseEnv("/Users/someone", "/tmp"), secrets, settings: { whisperThreads: 8 }, firstLaunch };
}

/** Launches nothing: records the command, and exits when the test says. */
function recorder() {
  const commands = new Map<string, Command>();
  const exits = new Map<string, (exit: Exit) => void>();
  const launch = (name: string, command: Command): Handle => {
    commands.set(name, command);
    const exited = new Promise<Exit>((resolve) => exits.set(name, resolve));
    return { pid: 1, exited, kill: () => {}, tail: () => "" };
  };
  return { commands, exits, launch };
}

describe("the units", () => {
  it("make the cluster and the database on the first launch, before anything else uses them", () => {
    const specs = buildSpecs(context(true), recorder().launch);
    const needs = Object.fromEntries(specs.map((s) => [s.name, s.needs]));
    assert.deepEqual(needs, {
      initdb: [],
      postgres: ["initdb"],
      createdb: ["postgres"],
      migrate: ["createdb"],
      seed: ["migrate"],
      api: ["seed"],
      asr: [],
      tts: [],
      pron: [],
      "asr-multi": [],
    });
  });

  it("start from Postgres on every later launch", () => {
    const specs = buildSpecs(context(false), recorder().launch);
    assert.deepEqual(
      specs.map((s) => s.name),
      ["postgres", "migrate", "seed", "api", "asr", "tts", "pron", "asr-multi"],
    );
    assert.deepEqual(specs.find((s) => s.name === "migrate")!.needs, ["postgres"]);
  });

  it("run Postgres on 127.0.0.1 only, with no socket, and stop it with its fast shutdown", () => {
    const { commands, launch } = recorder();
    const postgres = buildSpecs(context(false), launch).find((s) => s.name === "postgres")!;
    postgres.launch();
    const command = commands.get("postgres")!;
    assert.equal(command.file, "/R/pg/bin/postgres");
    assert.deepEqual(command.args, ["-D", p.cluster, "-p", "5443", "-c", "listen_addresses=127.0.0.1", "-c", "unix_socket_directories="]);
    assert.equal(command.env.TZ, "Etc/UTC");
    assert.equal(postgres.stopSignal, "SIGINT");
  });

  it("give initdb the password in a 0600 file, removed once initdb is done", async () => {
    const { commands, exits, launch } = recorder();
    const initdb = buildSpecs(context(true), launch).find((s) => s.name === "initdb")!;
    initdb.launch();
    const args = commands.get("initdb")!.args;
    const pwfile = args.find((a) => a.startsWith("--pwfile="))!.slice("--pwfile=".length);
    assert.equal(readFileSync(pwfile, "utf8"), "pw-123\n");
    assert.equal(statSync(pwfile).mode & 0o777, 0o600);
    for (const flag of ["-U", "speaklab", "-E", "UTF8", "--locale=en_US.UTF-8", "--auth-host=scram-sha-256", "--auth-local=scram-sha-256"]) {
      assert.ok(args.includes(flag), `initdb ${flag}`);
    }
    assert.ok(!args.join(" ").includes("pw-123"), "the password is never an argument");
    exits.get("initdb")!({ code: 0, signal: null });
    await new Promise((resolve) => setImmediate(resolve));
    assert.ok(!existsSync(pwfile));
  });

  it("run the migration, the seed and the five services from the bundle's interpreter", () => {
    const { commands, launch } = recorder();
    for (const spec of buildSpecs(context(false), launch)) spec.launch();
    assert.deepEqual(commands.get("migrate")!.args, ["-m", "alembic", "upgrade", "head"]);
    assert.deepEqual(commands.get("seed")!.args, ["-m", "scripts.seed"]);
    assert.deepEqual(commands.get("api")!.args, ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8012"]);
    for (const [service, port, code] of [["asr", "8111", "asr"], ["tts", "8112", "tts"], ["pron", "8113", "pron"], ["asr-multi", "8114", "asr"]] as const) {
      const command = commands.get(service)!;
      assert.deepEqual(command.args, ["-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", port]);
      assert.equal(command.cwd, `/R/src/infra/${code}`);
      assert.equal(command.env.PYTHONPATH, `/R/envs/${code}`);
    }
    for (const name of ["migrate", "seed", "api"]) {
      const command = commands.get(name)!;
      assert.equal(command.file, "/R/python/bin/python3.12");
      assert.equal(command.cwd, "/R/src/api");
      assert.match(command.env.DATABASE_URL!, /@127\.0\.0\.1:5443\/speaklab$/);
    }
  });

  it("say, in words, that data from a newer SpeakLab is refused", () => {
    const tail = "alembic.util.exc.CommandError: Can't locate revision identified by '0009'";
    assert.match(explainMigration(tail)!, /newer SpeakLab/);
    assert.equal(explainMigration("connection refused"), undefined);
    const migrate = buildSpecs(context(false), recorder().launch).find((s) => s.name === "migrate")!;
    assert.equal(migrate.explain, explainMigration);
  });
});
