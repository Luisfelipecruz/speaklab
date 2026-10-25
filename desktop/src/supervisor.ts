// The Compose graph, run as processes. A unit starts when everything it needs is done (a
// job) or ready (a service): docker-compose.yml's depends_on with a health check. A
// service that exits is started again after a growing pause, and left down after too many
// exits in a short time. While it is down, the services that need it, directly or through
// jobs, are stopped and wait for it, so the API never runs on against a database that
// went away under it. Stopping goes the other way: a unit is stopped only once nothing
// still running depends on it, directly or through others, so Postgres goes last.
//
// It knows nothing of Electron, child_process or the disk: units are launched, probed and
// timed through the functions it is given, which is what lets the tests drive it with fakes.

export type Kind = "job" | "service";
export type State = "waiting" | "starting" | "ready" | "done" | "restarting" | "failed" | "stopping" | "stopped";

export interface Exit {
  code: number | null;
  signal: string | null;
}

export interface Handle {
  readonly pid: number;
  readonly exited: Promise<Exit>;
  kill(signal: NodeJS.Signals): void;
  /** The last lines the process wrote, for explaining a failure. */
  tail(): string;
}

export interface Spec {
  name: string;
  kind: Kind;
  needs: readonly string[];
  launch(): Handle;
  /** A service is ready once this answers true; without it, as soon as it is launched. */
  ready?(): Promise<boolean>;
  /** SIGTERM unless set; Postgres takes SIGINT, its fast shutdown. */
  stopSignal?: NodeJS.Signals;
  /** How long a stop may take before SIGKILL. */
  stopTimeoutMs?: number;
  /** What a failed job's output means, in words for the person. */
  explain?(tail: string): string | undefined;
}

export interface Change {
  name: string;
  state: State;
  detail?: string;
}

export interface Clock {
  now(): number;
  sleep(ms: number): Promise<void>;
}

export interface Options {
  clock?: Clock;
  pollMs?: number;
  readyTimeoutMs?: number;
  backoffMs?: readonly number[];
  giveUp?: { exits: number; withinMs: number };
  /** Ready for this long, and the next exit starts the pauses from the first again. */
  stableMs?: number;
}

const realClock: Clock = {
  now: () => Date.now(),
  sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
};

interface Unit {
  spec: Spec;
  state: State;
  handle?: Handle;
  alive: boolean;
  /** Stopped by the supervisor because something it needs went down. */
  bounced: boolean;
  exits: number[];
  attempt: number;
  settled: Promise<boolean>;
  settle(ok: boolean): void;
}

export class Supervisor {
  private readonly units = new Map<string, Unit>();
  private readonly waiters = new Set<() => void>();
  private readonly clock: Clock;
  private readonly pollMs: number;
  private readonly readyTimeoutMs: number;
  private readonly backoffMs: readonly number[];
  private readonly giveUp: { exits: number; withinMs: number };
  private readonly stableMs: number;
  private readonly onChange: (change: Change) => void;
  private stopping = false;

  constructor(specs: readonly Spec[], onChange: (change: Change) => void, options: Options = {}) {
    this.onChange = onChange;
    this.clock = options.clock ?? realClock;
    this.pollMs = options.pollMs ?? 50;
    this.readyTimeoutMs = options.readyTimeoutMs ?? 600_000;
    this.backoffMs = options.backoffMs ?? [1000, 2000, 4000, 8000, 16000, 30000];
    this.giveUp = options.giveUp ?? { exits: 5, withinMs: 300_000 };
    this.stableMs = options.stableMs ?? 60_000;
    for (const spec of specs) {
      let settle: (ok: boolean) => void = () => {};
      const settled = new Promise<boolean>((resolve) => (settle = resolve));
      this.units.set(spec.name, { spec, state: "waiting", alive: false, bounced: false, exits: [], attempt: 0, settled, settle });
    }
    for (const unit of this.units.values()) {
      for (const need of unit.spec.needs) {
        if (!this.units.has(need)) throw new Error(`${unit.spec.name} needs ${need}, which is not a unit`);
      }
      if (this.needs(unit, unit.spec.name)) throw new Error(`${unit.spec.name} needs itself`);
    }
  }

  state(name: string): State | undefined {
    return this.units.get(name)?.state;
  }

  /** True once this unit is first done or ready; false if it failed first, or a stop began. */
  settled(name: string): Promise<boolean> {
    const unit = this.units.get(name);
    if (!unit) throw new Error(`${name} is not a unit`);
    return unit.settled;
  }

  /** Resolves with the names that failed, once every unit is done, ready or failed. */
  async start(): Promise<string[]> {
    const settled = [...this.units.values()].map((unit) => {
      void this.run(unit);
      return unit.settled;
    });
    await Promise.all(settled);
    return [...this.units.values()].filter((u) => u.state === "failed").map((u) => u.spec.name);
  }

  /** Stops whatever runs, dependents first; resolves once every process has exited. */
  async stop(): Promise<void> {
    this.stopping = true;
    // Whatever has not settled will not now, and whatever waits on it must not wait on.
    for (const unit of this.units.values()) unit.settle(false);
    this.wake();
    for (;;) {
      const alive = [...this.units.values()].filter((u) => u.alive);
      if (alive.length === 0) return;
      const layer = alive.filter((u) => !alive.some((other) => other !== u && this.needs(other, u.spec.name)));
      await Promise.all(layer.map((u) => this.stopUnit(u)));
    }
  }

  /** Whether `unit` needs `name`, directly or through the units it needs. */
  private needs(unit: Unit, name: string, seen = new Set<string>()): boolean {
    for (const need of unit.spec.needs) {
      if (need === name) return true;
      if (seen.has(need)) continue;
      seen.add(need);
      if (this.needs(this.units.get(need)!, name, seen)) return true;
    }
    return false;
  }

  /** A service is up while it is ready; a job once it is done, while what it needed is up. */
  private up(unit: Unit): boolean {
    if (unit.spec.kind === "service") return unit.state === "ready";
    return unit.state === "done" && unit.spec.needs.every((n) => this.up(this.units.get(n)!));
  }

  /** The units it needs, directly or through others, that have failed. */
  private failedNeeds(unit: Unit): string[] {
    const found = new Set<string>();
    const walk = (u: Unit, seen: Set<string>): void => {
      for (const name of u.spec.needs) {
        if (seen.has(name)) continue;
        seen.add(name);
        const need = this.units.get(name)!;
        if (need.state === "failed") found.add(name);
        else walk(need, seen);
      }
    };
    walk(unit, new Set());
    return [...found];
  }

  /** The services it needs, directly or through jobs, that are not ready. */
  private downNeeds(unit: Unit): string[] {
    const found = new Set<string>();
    const walk = (u: Unit): void => {
      for (const name of u.spec.needs) {
        const need = this.units.get(name)!;
        if (need.spec.kind === "job") walk(need);
        else if (need.state !== "ready") found.add(name);
      }
    };
    walk(unit);
    return [...found];
  }

  private set(unit: Unit, state: State, detail?: string): void {
    unit.state = state;
    this.onChange(detail === undefined ? { name: unit.spec.name, state } : { name: unit.spec.name, state, detail });
    this.wake();
  }

  private wake(): void {
    for (const waiter of [...this.waiters]) waiter();
  }

  /** True once everything it needs is up; false if one of them failed, or a stop began. */
  private needsUp(unit: Unit): Promise<boolean> {
    return new Promise((resolve) => {
      const check = (): boolean => {
        if (this.stopping || this.failedNeeds(unit).length > 0) resolve(false);
        else if (unit.spec.needs.every((n) => this.up(this.units.get(n)!))) resolve(true);
        else return false;
        return true;
      };
      if (check()) return;
      const waiter = (): void => {
        if (check()) this.waiters.delete(waiter);
      };
      this.waiters.add(waiter);
    });
  }

  /** It cannot start because something it needs failed: it fails too, naming what. */
  private blocked(unit: Unit): void {
    if (!this.stopping) this.set(unit, "failed", `needs ${this.failedNeeds(unit).join(", ")}`);
    unit.settle(false);
  }

  private launch(unit: Unit): Handle {
    this.set(unit, "starting");
    const handle = unit.spec.launch();
    unit.handle = handle;
    unit.alive = true;
    void handle.exited.then(() => {
      if (unit.handle === handle) unit.alive = false;
    });
    return handle;
  }

  private async run(unit: Unit): Promise<void> {
    const needs = await Promise.all(unit.spec.needs.map((n) => this.units.get(n)!.settled));
    if (this.stopping) return unit.settle(false);
    if (needs.some((ok) => !ok)) return this.blocked(unit);
    if (unit.spec.kind === "job") return this.runJob(unit);
    for (;;) {
      if (!(await this.needsUp(unit))) return this.blocked(unit);
      const handle = this.launch(unit);
      const outcome = await this.waitReady(unit, handle);
      if (outcome === "ready") {
        const readyAt = this.clock.now();
        this.set(unit, "ready");
        unit.settle(true);
        await handle.exited;
        if (this.clock.now() - readyAt >= this.stableMs) unit.attempt = 0;
      } else if (outcome === "timeout") {
        handle.kill("SIGKILL");
      }
      await handle.exited;
      if (this.stopping) return;
      if (unit.bounced) {
        // Not an exit of its own: it starts again once what it needs is back.
        unit.bounced = false;
        const down = this.downNeeds(unit);
        this.set(unit, "waiting", down.length > 0 ? `needs ${down.join(", ")}` : undefined);
        continue;
      }
      this.bounce(unit);
      const pause = this.recordExit(unit, outcome === "timeout" ? "was not ready in time" : undefined);
      if (pause === null) return;
      await this.clock.sleep(pause);
      if (this.stopping) return;
    }
  }

  private async runJob(unit: Unit): Promise<void> {
    const handle = this.launch(unit);
    const exit = await handle.exited;
    if (exit.code === 0) {
      this.set(unit, "done");
      unit.settle(true);
      return;
    }
    const detail = unit.spec.explain?.(handle.tail()) ?? `exited with ${exit.code ?? exit.signal}`;
    this.set(unit, "failed", detail);
    unit.settle(false);
  }

  private async waitReady(unit: Unit, handle: Handle): Promise<"ready" | "exited" | "timeout"> {
    if (!unit.spec.ready) return "ready";
    let exited = false;
    void handle.exited.then(() => (exited = true));
    const deadline = this.clock.now() + this.readyTimeoutMs;
    while (!exited && !this.stopping && !unit.bounced) {
      const ok = await unit.spec.ready().catch(() => false);
      if (exited || unit.bounced) break;
      if (ok) return "ready";
      if (this.clock.now() >= deadline) return "timeout";
      await this.clock.sleep(this.pollMs);
    }
    return "exited";
  }

  /** The services that need this one, directly or through jobs, stop until it is back. */
  private bounce(unit: Unit): void {
    for (const other of this.units.values()) {
      if (other.spec.kind !== "service" || !other.alive || !other.handle) continue;
      if (!this.needs(other, unit.spec.name)) continue;
      other.bounced = true;
      this.set(other, "stopping", `${unit.spec.name} stopped`);
      void this.terminate(other, other.handle);
    }
  }

  /** The pause before the next start, or null when it has exited too often to try again. */
  private recordExit(unit: Unit, reason?: string): number | null {
    const now = this.clock.now();
    unit.exits = [...unit.exits, now].filter((t) => now - t <= this.giveUp.withinMs);
    if (unit.exits.length >= this.giveUp.exits) {
      const minutes = Math.round(this.giveUp.withinMs / 60_000);
      this.set(unit, "failed", reason ?? `exited ${unit.exits.length} times in ${minutes} minutes`);
      unit.settle(false);
      return null;
    }
    const pause = this.backoffMs[Math.min(unit.attempt, this.backoffMs.length - 1)] ?? 0;
    unit.attempt += 1;
    this.set(unit, "restarting", reason ?? `exited; starting again in ${Math.round(pause / 1000)} s`);
    return pause;
  }

  /** Its stop signal, then SIGKILL once its time is up; resolves when it has exited. */
  private async terminate(unit: Unit, handle: Handle): Promise<void> {
    let over = false;
    void handle.exited.then(() => (over = true));
    handle.kill(unit.spec.stopSignal ?? "SIGTERM");
    const deadline = this.clock.now() + (unit.spec.stopTimeoutMs ?? 10_000);
    while (!over && this.clock.now() < deadline) await this.clock.sleep(this.pollMs);
    if (!over) handle.kill("SIGKILL");
    await handle.exited;
  }

  private async stopUnit(unit: Unit): Promise<void> {
    const handle = unit.handle;
    if (!handle || !unit.alive) return;
    this.set(unit, "stopping");
    await this.terminate(unit, handle);
    unit.alive = false;
    this.set(unit, "stopped");
  }
}
