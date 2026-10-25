import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { type Clock, type Exit, type Handle, type Spec, Supervisor } from "../src/supervisor.ts";

/** A process the test ends: it exits when told to, or when it receives a signal it obeys. */
class FakeProcess implements Handle {
  static next = 1000;
  readonly pid = FakeProcess.next++;
  readonly signals: string[] = [];
  readonly exited: Promise<Exit>;
  private readonly obeys: readonly string[];
  private readonly output: string;
  private finish!: (exit: Exit) => void;
  private over = false;

  constructor(obeys: readonly string[] = ["SIGTERM", "SIGINT", "SIGKILL"], output = "") {
    this.obeys = obeys;
    this.output = output;
    this.exited = new Promise((resolve) => (this.finish = resolve));
  }

  exit(code: number | null = 0, signal: string | null = null): void {
    if (this.over) return;
    this.over = true;
    this.finish({ code, signal });
  }

  kill(signal: NodeJS.Signals): void {
    this.signals.push(signal);
    if (this.obeys.includes(signal)) this.exit(null, signal);
  }

  tail(): string {
    return this.output;
  }
}

/** Time that passes only when something sleeps; each sleep yields to the event loop. */
function fakeClock(): Clock & { slept: number[] } {
  let now = 0;
  const slept: number[] = [];
  return {
    slept,
    now: () => now,
    sleep: async (ms) => {
      slept.push(ms);
      now += ms;
      await new Promise((resolve) => setImmediate(resolve));
    },
  };
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

interface Built {
  specs: Spec[];
  launched: string[];
  processes: Map<string, FakeProcess[]>;
  ready: Map<string, boolean>;
}

/** The desktop graph's shape: initdb → postgres → migrate → seed → api, and three models. */
function graph(jobExit: (name: string) => number = () => 0, output: (name: string) => string = () => ""): Built {
  const launched: string[] = [];
  const processes = new Map<string, FakeProcess[]>();
  const ready = new Map<string, boolean>();
  const spec = (name: string, kind: "job" | "service", needs: string[], extra: Partial<Spec> = {}): Spec => ({
    name,
    kind,
    needs,
    launch: () => {
      launched.push(name);
      const p = new FakeProcess(undefined, output(name));
      processes.set(name, [...(processes.get(name) ?? []), p]);
      if (kind === "job") queueMicrotask(() => p.exit(jobExit(name)));
      return p;
    },
    ...(kind === "service" ? { ready: async () => ready.get(name) ?? true } : {}),
    ...extra,
  });
  const specs = [
    spec("initdb", "job", []),
    spec("postgres", "service", ["initdb"], { stopSignal: "SIGINT", stopTimeoutMs: 30_000 }),
    spec("migrate", "job", ["postgres"]),
    spec("seed", "job", ["migrate"]),
    spec("api", "service", ["seed"]),
    spec("asr", "service", []),
    spec("tts", "service", []),
    spec("pron", "service", []),
  ];
  return { specs, launched, processes, ready };
}

describe("the supervisor", () => {
  it("starts each unit once what it needs is done or ready, and the models at once", async () => {
    const { specs, launched } = graph();
    const failed = await new Supervisor(specs, () => {}, { clock: fakeClock() }).start();
    assert.deepEqual(failed, []);
    const at = (name: string) => launched.indexOf(name);
    assert.ok(at("initdb") < at("postgres"));
    assert.ok(at("postgres") < at("migrate"));
    assert.ok(at("migrate") < at("seed"));
    assert.ok(at("seed") < at("api"));
    for (const model of ["asr", "tts", "pron"]) assert.ok(at(model) < at("migrate"), `${model} waited`);
  });

  it("does not start what needs a service until the service answers ready", async () => {
    const { specs, launched, ready } = graph();
    ready.set("postgres", false);
    const supervisor = new Supervisor(specs, () => {}, { clock: fakeClock(), readyTimeoutMs: 1e12 });
    const started = supervisor.start();
    for (let i = 0; i < 20; i++) await tick();
    assert.ok(launched.includes("postgres"));
    assert.ok(!launched.includes("migrate"));
    assert.equal(supervisor.state("postgres"), "starting");
    ready.set("postgres", true);
    assert.deepEqual(await started, []);
    assert.ok(launched.includes("api"));
  });

  it("fails what needs a failed job, and says what the job's output means", async () => {
    const changes: { name: string; state: string; detail?: string }[] = [];
    const { specs, launched } = graph(
      (name) => (name === "migrate" ? 1 : 0),
      (name) => (name === "migrate" ? "Can't locate revision identified by '0009'" : ""),
    );
    const migrate = specs.find((s) => s.name === "migrate")!;
    migrate.explain = (tail) => (tail.includes("Can't locate revision") ? "newer-schema" : undefined);
    const failed = await new Supervisor(specs, (c) => changes.push(c), { clock: fakeClock() }).start();
    assert.deepEqual(failed.sort(), ["api", "migrate", "seed"]);
    assert.ok(!launched.includes("seed"));
    assert.ok(!launched.includes("api"));
    assert.deepEqual(changes.find((c) => c.name === "migrate" && c.state === "failed")?.detail, "newer-schema");
    assert.deepEqual(changes.find((c) => c.name === "seed" && c.state === "failed")?.detail, "needs migrate");
  });

  it("starts a service that exits again, after pauses that grow", async () => {
    const clock = fakeClock();
    const { specs, processes } = graph();
    const supervisor = new Supervisor(specs, () => {}, { clock, backoffMs: [1000, 2000, 4000] });
    await supervisor.start();
    for (let round = 0; round < 3; round++) {
      processes.get("asr")!.at(-1)!.exit(1);
      for (let i = 0; i < 20; i++) await tick();
    }
    assert.equal(processes.get("asr")!.length, 4);
    assert.deepEqual(
      clock.slept.filter((ms) => ms >= 1000),
      [1000, 2000, 4000],
    );
    assert.equal(supervisor.state("asr"), "ready");
  });

  it("leaves a service down that exits too often, and says so", async () => {
    const changes: { name: string; state: string; detail?: string }[] = [];
    const { specs, processes } = graph();
    const supervisor = new Supervisor(specs, (c) => changes.push(c), {
      clock: fakeClock(),
      backoffMs: [10],
      giveUp: { exits: 3, withinMs: 300_000 },
    });
    await supervisor.start();
    for (let round = 0; round < 3; round++) {
      processes.get("tts")!.at(-1)!.exit(1);
      for (let i = 0; i < 20; i++) await tick();
    }
    assert.equal(supervisor.state("tts"), "failed");
    assert.equal(processes.get("tts")!.length, 3);
    assert.match(changes.filter((c) => c.name === "tts").at(-1)!.detail!, /3 times/);
  });

  it("stops the API and the models before Postgres, and Postgres with its own signal", async () => {
    const { specs, processes } = graph();
    const supervisor = new Supervisor(specs, () => {}, { clock: fakeClock() });
    await supervisor.start();
    const order: string[] = [];
    for (const [name, list] of processes) {
      const p = list.at(-1)!;
      const kill = p.kill.bind(p);
      p.kill = (signal) => {
        order.push(name);
        kill(signal);
      };
    }
    await supervisor.stop();
    assert.equal(order.at(-1), "postgres");
    assert.deepEqual(new Set(order.slice(0, -1)), new Set(["api", "asr", "tts", "pron"]));
    assert.deepEqual(processes.get("postgres")!.at(-1)!.signals, ["SIGINT"]);
    assert.deepEqual(processes.get("api")!.at(-1)!.signals, ["SIGTERM"]);
    for (const name of ["postgres", "api", "asr"]) assert.equal(supervisor.state(name), "stopped");
  });

  it("kills a process that ignores its stop signal once the time is up", async () => {
    const stubborn = new FakeProcess(["SIGKILL"]);
    const spec: Spec = { name: "asr", kind: "service", needs: [], launch: () => stubborn, stopTimeoutMs: 5000 };
    const supervisor = new Supervisor([spec], () => {}, { clock: fakeClock() });
    await supervisor.start();
    await supervisor.stop();
    assert.deepEqual(stubborn.signals, ["SIGTERM", "SIGKILL"]);
  });

  it("starts nothing again while it is stopping", async () => {
    const { specs, processes } = graph();
    const supervisor = new Supervisor(specs, () => {}, { clock: fakeClock(), backoffMs: [10] });
    await supervisor.start();
    const stopped = supervisor.stop();
    processes.get("pron")!.at(-1)!.exit(1);
    await stopped;
    for (let i = 0; i < 20; i++) await tick();
    assert.equal(processes.get("pron")!.length, 1);
  });

  it("lets start() return when a stop comes before a service was ever ready", async () => {
    const { specs, ready, launched } = graph();
    ready.set("postgres", false);
    const supervisor = new Supervisor(specs, () => {}, { clock: fakeClock(), readyTimeoutMs: 1e12 });
    const started = supervisor.start();
    for (let i = 0; i < 10; i++) await tick();
    await supervisor.stop();
    await started;
    assert.ok(!launched.includes("migrate"));
  });

  it("stops the API while Postgres is down, and starts it once Postgres is ready again", async () => {
    const changes: { name: string; state: string; detail?: string }[] = [];
    const { specs, processes, launched, ready } = graph();
    const supervisor = new Supervisor(specs, (c) => changes.push(c), { clock: fakeClock(), backoffMs: [1000], readyTimeoutMs: 1e12 });
    await supervisor.start();
    ready.set("postgres", false);
    processes.get("postgres")!.at(-1)!.exit(1);
    for (let i = 0; i < 40; i++) await tick();
    assert.deepEqual(processes.get("api")![0]!.signals, ["SIGTERM"]);
    assert.equal(processes.get("postgres")!.length, 2);
    assert.equal(processes.get("api")!.length, 1, "the API waits for Postgres to be ready");
    assert.equal(supervisor.state("api"), "waiting");
    ready.set("postgres", true);
    for (let i = 0; i < 40; i++) await tick();
    assert.deepEqual(launched.slice(-2), ["postgres", "api"]);
    assert.equal(supervisor.state("api"), "ready");
    assert.ok(!changes.some((c) => c.name === "api" && c.state === "restarting"), "not counted as an exit of the API's");
    for (const job of ["initdb", "migrate", "seed"]) assert.equal(processes.get(job)!.length, 1, `${job} ran once`);
    for (const model of ["asr", "tts", "pron"]) assert.equal(processes.get(model)!.length, 1, `${model} kept running`);
  });

  it("fails the API, naming Postgres, once Postgres is left down", async () => {
    const changes: { name: string; state: string; detail?: string }[] = [];
    const { specs, processes } = graph();
    const supervisor = new Supervisor(specs, (c) => changes.push(c), {
      clock: fakeClock(),
      backoffMs: [10],
      giveUp: { exits: 2, withinMs: 300_000 },
    });
    await supervisor.start();
    for (let round = 0; round < 2; round++) {
      processes.get("postgres")!.at(-1)!.exit(1);
      for (let i = 0; i < 40; i++) await tick();
    }
    assert.equal(supervisor.state("postgres"), "failed");
    assert.equal(supervisor.state("api"), "failed");
    assert.equal(changes.filter((c) => c.name === "api").at(-1)!.detail, "needs postgres");
    assert.equal(supervisor.state("asr"), "ready");
  });

  it("says the API is up while a model service is still loading", async () => {
    const { specs, ready } = graph();
    ready.set("pron", false);
    const supervisor = new Supervisor(specs, () => {}, { clock: fakeClock(), readyTimeoutMs: 1e12 });
    const started = supervisor.start();
    assert.equal(await supervisor.settled("api"), true);
    assert.equal(supervisor.state("pron"), "starting");
    ready.set("pron", true);
    assert.deepEqual(await started, []);
    assert.throws(() => supervisor.settled("web"), /not a unit/);
  });

  it("says the API failed as soon as it does, naming what it needed", async () => {
    const { specs, ready } = graph((name) => (name === "migrate" ? 1 : 0));
    ready.set("pron", false);
    const supervisor = new Supervisor(specs, () => {}, { clock: fakeClock(), readyTimeoutMs: 1e12 });
    void supervisor.start();
    assert.equal(await supervisor.settled("api"), false);
    assert.equal(supervisor.state("pron"), "starting");
    await supervisor.stop();
  });

  it("refuses a graph that names a unit that does not exist", () => {
    const spec: Spec = { name: "api", kind: "service", needs: ["seed"], launch: () => new FakeProcess() };
    assert.throws(() => new Supervisor([spec], () => {}), /needs seed/);
  });

  it("refuses a graph in which a unit needs itself", () => {
    const a: Spec = { name: "a", kind: "service", needs: ["b"], launch: () => new FakeProcess() };
    const b: Spec = { name: "b", kind: "service", needs: ["a"], launch: () => new FakeProcess() };
    assert.throws(() => new Supervisor([a, b], () => {}), /needs itself/);
  });
});
