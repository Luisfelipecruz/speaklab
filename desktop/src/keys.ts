// fn, turned into what the person meant. The helper (native/keys.swift) reports four kinds
// of line and nothing else: Input Monitoring's state, fn down with the app in front, fn
// up, and that another key went down while fn was held. This module reads those lines and
// decides:
//
//   hold        fn down for 180 ms with no other key: say it, release to finish
//   hands-free  two taps within 350 ms; the next tap, or the panel's Done, finishes
//   cancel      another key while fn is held (a shortcut), or Esc
//
// The microphone opens on fn down, before it is a hold, so the first word is not lost
// while the hold is being decided; a tap that comes to nothing discards what it heard.
// The timing is done against a clock it is given, which is what lets the tests script it.

import { type ChildProcess, spawn } from "node:child_process";
import { createInterface } from "node:readline";

export const HOLD_MS = 180;
export const DOUBLE_TAP_MS = 350;

export type KeyEvent =
  | { t: "access"; granted: boolean }
  | { t: "down"; app: string | null; ms?: number }
  | { t: "up"; ms?: number }
  | { t: "chord"; ms?: number };

/** One line of the helper's output, or null when it is not one of its four kinds. */
export function parseLine(line: string): KeyEvent | null {
  let value: unknown;
  try {
    value = JSON.parse(line);
  } catch {
    return null;
  }
  if (!value || typeof value !== "object") return null;
  const event = value as Record<string, unknown>;
  const ms = typeof event.ms === "number" ? { ms: event.ms } : {};
  switch (event.t) {
    case "access":
      return typeof event.granted === "boolean" ? { t: "access", granted: event.granted } : null;
    case "down":
      return { t: "down", app: typeof event.app === "string" ? event.app : null, ...ms };
    case "up":
      return { t: "up", ...ms };
    case "chord":
      return { t: "chord", ...ms };
    default:
      return null;
  }
}

export interface Timers {
  set(callback: () => void, ms: number): unknown;
  clear(timer: unknown): void;
}

export const realTimers: Timers = {
  set: (callback, ms) => setTimeout(callback, ms),
  clear: (timer) => clearTimeout(timer as ReturnType<typeof setTimeout>),
};

/** What the intentions are told to do. Each is called at most once per press or tap. */
export interface Intents {
  /** fn went down: open the microphone and warm the model, before anything is decided. */
  arm(app: string | null): void;
  /** Held long enough to mean it: show the panel listening. */
  hold(): void;
  /** Two taps: listening until the next tap or Done. */
  handsFree(): void;
  /** Released after a hold, or the tap that ends hands-free: send what was said. */
  finish(): void;
  /** A shortcut, Esc, or a tap that came to nothing: discard it. */
  cancel(): void;
}

type Phase = "idle" | "pressed" | "tapped" | "holding" | "handsFree" | "ending";

export class Intentions {
  private phase: Phase = "idle";
  private timer: unknown = null;
  private readonly intents: Intents;
  private readonly timers: Timers;

  constructor(intents: Intents, timers: Timers = realTimers) {
    this.intents = intents;
    this.timers = timers;
  }

  get state(): Phase {
    return this.phase;
  }

  /** Listening, held or hands-free: where Esc means cancel. */
  get listening(): boolean {
    return this.phase === "holding" || this.phase === "handsFree";
  }

  private wait(ms: number, then: () => void): void {
    this.stopTimer();
    this.timer = this.timers.set(() => {
      this.timer = null;
      then();
    }, ms);
  }

  private stopTimer(): void {
    if (this.timer !== null) this.timers.clear(this.timer);
    this.timer = null;
  }

  key(event: KeyEvent): void {
    if (event.t === "down") this.down(event.app);
    else if (event.t === "up") this.up();
    else if (event.t === "chord") this.chord();
  }

  private down(app: string | null): void {
    switch (this.phase) {
      case "idle":
        this.phase = "pressed";
        this.intents.arm(app);
        this.wait(HOLD_MS, () => {
          this.phase = "holding";
          this.intents.hold();
        });
        return;
      case "tapped":
        // The second tap: hands-free, from the first tap's microphone on.
        this.stopTimer();
        this.phase = "handsFree";
        this.intents.handsFree();
        return;
      case "handsFree":
        this.phase = "ending";
        this.intents.finish();
        return;
      default:
        return;
    }
  }

  private up(): void {
    switch (this.phase) {
      case "pressed":
        this.phase = "tapped";
        this.wait(DOUBLE_TAP_MS, () => this.reset(true));
        return;
      case "holding":
        this.phase = "idle";
        this.intents.finish();
        return;
      case "ending":
        this.phase = "idle";
        return;
      default:
        return;
    }
  }

  private chord(): void {
    if (this.phase === "pressed" || this.phase === "holding") this.reset(true);
  }

  /** Esc, or the panel's own cancel. */
  escape(): void {
    if (this.phase !== "idle") this.reset(true);
  }

  /** The panel's Done, for hands-free without fn. */
  done(): void {
    if (this.phase === "handsFree") {
      this.stopTimer();
      this.phase = "idle";
      this.intents.finish();
    }
  }

  /** Hands-free begun from the panel, by Speak instead: a tap of fn ends it, as after two taps. */
  listenWithoutKey(): void {
    if (this.phase !== "idle") return;
    this.phase = "handsFree";
  }

  /** Listening stopped without the key, at the time limit: the next press starts afresh. */
  forget(): void {
    this.reset(false);
  }

  private reset(cancelled: boolean): void {
    this.stopTimer();
    const was = this.phase;
    this.phase = "idle";
    if (cancelled && was !== "idle") this.intents.cancel();
  }
}

export interface HelperOptions {
  file: string;
  args?: string[];
  onEvent(event: KeyEvent): void;
  onExit?(code: number | null): void;
  /** Spawns the helper; replaced in the tests. */
  start?: (file: string, args: string[]) => ChildProcess;
}

/**
 * The helper as a process: started, read line by line, and started again a second after it
 * exits for any reason but being asked to quit. It exits with 3 when Input Monitoring has
 * just been granted and its tap needs a fresh process.
 */
export class KeyHelper {
  private child: ChildProcess | null = null;
  private stopping = false;
  private restart: ReturnType<typeof setTimeout> | null = null;
  private readonly options: HelperOptions;

  constructor(options: HelperOptions) {
    this.options = options;
  }

  start(): void {
    this.stopping = false;
    const begin = this.options.start ?? ((file, args) => spawn(file, args, { stdio: ["pipe", "pipe", "ignore"] }));
    const child = begin(this.options.file, this.options.args ?? []);
    this.child = child;
    if (child.stdout) {
      createInterface({ input: child.stdout }).on("line", (line) => {
        const event = parseLine(line);
        if (event) this.options.onEvent(event);
      });
    }
    child.once("exit", (code) => {
      if (this.child === child) this.child = null;
      this.options.onExit?.(code);
      if (!this.stopping) this.restart = setTimeout(() => this.start(), 1000);
    });
    child.once("error", () => {
      // A helper that cannot start is reported by its exit; nothing else to do here.
    });
    // Told to quit after it has gone, it can no longer be written to. It needs no telling,
    // and the write's error, unheard, would stop the app's quit behind Electron's alert.
    child.stdin?.on("error", () => {});
  }

  stop(): void {
    this.stopping = true;
    if (this.restart) clearTimeout(this.restart);
    this.child?.stdin?.end("quit\n");
    this.child = null;
  }
}
