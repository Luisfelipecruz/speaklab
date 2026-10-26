import assert from "node:assert/strict";
import type { ChildProcess } from "node:child_process";
import { EventEmitter } from "node:events";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { PassThrough, Writable } from "node:stream";
import { describe, it } from "node:test";

import { DOUBLE_TAP_MS, HOLD_MS, type Intents, Intentions, type KeyEvent, KeyHelper, parseLine } from "../src/keys.ts";
import { fakeTimers } from "./timers.ts";

const FIXTURE = join(import.meta.dirname, "fixtures", "keys.jsonl");

/** The helper as a process: its output written by the test, its input read back. */
class FakeHelper extends EventEmitter {
  readonly stdout = new PassThrough();
  readonly stdin: PassThrough | Writable;
  readonly args: string[];

  constructor(args: string[], stdin: PassThrough | Writable = new PassThrough()) {
    super();
    this.args = args;
    this.stdin = stdin;
  }

  heard(): string {
    return this.stdin instanceof PassThrough ? String(this.stdin.read() ?? "") : "";
  }
}

/** A pipe whose reader has gone, as a helper's stdin is once the helper has exited. */
function gonePipe(): Writable {
  return new Writable({
    write(_chunk, _encoding, callback) {
      callback(Object.assign(new Error("write EPIPE"), { code: "EPIPE" }));
    },
  });
}

function helperRig(stdin?: () => Writable) {
  const started: FakeHelper[] = [];
  const events: KeyEvent[] = [];
  const exits: (number | null)[] = [];
  const helper = new KeyHelper({
    file: "/SpeakLab.app/Contents/MacOS/speaklab-keys",
    args: ["--no-request"],
    onEvent: (event) => events.push(event),
    onExit: (code) => exits.push(code),
    start: (_file, args) => {
      const child = new FakeHelper(args, stdin?.());
      started.push(child);
      return child as unknown as ChildProcess;
    },
  });
  return { helper, started, events, exits };
}

function recorded() {
  const calls: string[] = [];
  const intents: Intents = {
    arm: (app) => calls.push(`arm ${app}`),
    hold: () => calls.push("hold"),
    handsFree: () => calls.push("handsFree"),
    finish: () => calls.push("finish"),
    cancel: () => calls.push("cancel"),
  };
  return { calls, intents };
}

const down = { t: "down" as const, app: "Mail" };
const up = { t: "up" as const };
const chord = { t: "chord" as const };

describe("the helper's lines", () => {
  it("are read for their four kinds, and anything else is dropped", () => {
    const lines = readFileSync(FIXTURE, "utf8").trim().split("\n");
    assert.deepEqual(lines.map(parseLine), [
      { t: "access", granted: false },
      { t: "access", granted: true },
      { t: "down", app: "Mail", ms: 1792989259430 },
      { t: "up", ms: 1792989260110 },
      { t: "down", app: null },
      { t: "chord" },
      { t: "up" },
      null,
      null,
      { t: "down", app: null },
    ]);
  });

  it("never carry which key it was: the parsed events have no field for it", () => {
    const event = parseLine('{"t":"chord","key":"a","code":0}');
    assert.deepEqual(event, { t: "chord" });
  });
});

describe("the intentions", () => {
  it("open the microphone on fn down, and call it a hold at 180 ms", () => {
    const { calls, intents } = recorded();
    const timers = fakeTimers();
    const keys = new Intentions(intents, timers);

    keys.key(down);
    assert.deepEqual(calls, ["arm Mail"]);
    timers.advance(HOLD_MS - 1);
    assert.deepEqual(calls, ["arm Mail"]);
    timers.advance(1);
    keys.key(up);

    assert.deepEqual(calls, ["arm Mail", "hold", "finish"]);
    assert.equal(keys.state, "idle");
  });

  it("cancel a press that became a shortcut, before or after the hold", () => {
    for (const after of [50, HOLD_MS + 50]) {
      const { calls, intents } = recorded();
      const timers = fakeTimers();
      const keys = new Intentions(intents, timers);
      keys.key(down);
      timers.advance(after);
      keys.key(chord);
      keys.key(up);
      assert.equal(calls.at(-1), "cancel", `chord at ${after} ms`);
      assert.ok(!calls.includes("finish"));
    }
  });

  it("make two taps within 350 ms hands-free, ended by the next tap", () => {
    const { calls, intents } = recorded();
    const timers = fakeTimers();
    const keys = new Intentions(intents, timers);

    keys.key(down);
    timers.advance(60);
    keys.key(up);
    timers.advance(DOUBLE_TAP_MS - 100);
    keys.key(down);
    keys.key(up);
    assert.equal(keys.state, "handsFree");
    assert.ok(keys.listening);
    timers.advance(30_000);
    keys.key(down);
    keys.key(up);

    assert.deepEqual(calls, ["arm Mail", "handsFree", "finish"]);
    assert.equal(keys.state, "idle");
  });

  it("let one tap come to nothing, and discard what it opened", () => {
    const { calls, intents } = recorded();
    const timers = fakeTimers();
    const keys = new Intentions(intents, timers);

    keys.key(down);
    timers.advance(60);
    keys.key(up);
    timers.advance(DOUBLE_TAP_MS);

    assert.deepEqual(calls, ["arm Mail", "cancel"]);
  });

  it("take a second tap after the window as a new press", () => {
    const { calls, intents } = recorded();
    const timers = fakeTimers();
    const keys = new Intentions(intents, timers);

    keys.key(down);
    keys.key(up);
    timers.advance(DOUBLE_TAP_MS + 10);
    keys.key(down);
    timers.advance(HOLD_MS);

    assert.deepEqual(calls, ["arm Mail", "cancel", "arm Mail", "hold"]);
  });

  it("finish hands-free with Done, and cancel anything listening with Esc", () => {
    const { calls, intents } = recorded();
    const timers = fakeTimers();
    const keys = new Intentions(intents, timers);
    keys.key(down);
    keys.key(up);
    keys.key(down);
    keys.key(up);
    keys.done();
    assert.deepEqual(calls, ["arm Mail", "handsFree", "finish"]);

    keys.key(down);
    timers.advance(HOLD_MS);
    keys.escape();
    assert.deepEqual(calls.slice(3), ["arm Mail", "hold", "cancel"]);
    keys.escape();
    assert.equal(calls.length, 6, "Esc when nothing is listening does nothing");
    assert.equal(timers.pending, 0);
  });

  it("end hands-free begun from the panel with a tap of fn, as after two taps", () => {
    const { calls, intents } = recorded();
    const keys = new Intentions(intents, fakeTimers());

    keys.listenWithoutKey();
    keys.key(down);
    keys.key(up);

    assert.deepEqual(calls, ["finish"]);
    assert.equal(keys.state, "idle");
  });

  it("start afresh once listening has stopped at the time limit", () => {
    const { calls, intents } = recorded();
    const timers = fakeTimers();
    const keys = new Intentions(intents, timers);
    keys.key(down);
    keys.key(up);
    keys.key(down);
    keys.key(up);

    keys.forget();
    keys.key(down);
    timers.advance(HOLD_MS);

    assert.deepEqual(calls, ["arm Mail", "handsFree", "arm Mail", "hold"]);
  });

  it("ignore an up it never saw go down, as after a lost or repeated event", () => {
    const { calls, intents } = recorded();
    const keys = new Intentions(intents, fakeTimers());

    keys.key(up);
    keys.key(chord);

    assert.deepEqual(calls, []);
  });
});

describe("the helper process", () => {
  it("hands on its events line by line, and nothing that is not one", async () => {
    const { helper, started, events } = helperRig();
    helper.start();
    const child = started[0]!;
    const ended = new Promise((resolve) => child.stdout.once("end", resolve));
    child.stdout.end(readFileSync(FIXTURE));
    await ended;

    assert.deepEqual(child.args, ["--no-request"]);
    assert.deepEqual(
      events.map((event) => event.t),
      ["access", "access", "down", "up", "down", "chord", "up", "down"],
    );
  });

  it("is asked to quit on stop, and not started again when it does", (t) => {
    t.mock.timers.enable({ apis: ["setTimeout"] });
    const { helper, started, exits } = helperRig();
    helper.start();
    helper.stop();
    started[0]!.emit("exit", 0);
    t.mock.timers.tick(5_000);

    assert.equal(started[0]!.heard(), "quit\n");
    assert.equal(started.length, 1);
    assert.deepEqual(exits, [0]);
  });

  it("lets the app quit when it is told to quit after it has already gone", async () => {
    const { helper, started } = helperRig(gonePipe);
    helper.start();
    helper.stop();
    // The failed write's error is emitted after the call returns; unheard, it would stop
    // the app's quit behind Electron's alert for an uncaught exception.
    await new Promise((resolve) => setImmediate(resolve));

    assert.equal(started.length, 1);
  });

  it("is started again a second after it exits on its own, as after Input Monitoring is granted", (t) => {
    t.mock.timers.enable({ apis: ["setTimeout"] });
    const { helper, started, exits } = helperRig();
    helper.start();
    started[0]!.emit("exit", 3);

    t.mock.timers.tick(999);
    assert.equal(started.length, 1);
    t.mock.timers.tick(1);
    assert.equal(started.length, 2);
    assert.deepEqual(exits, [3]);

    helper.stop();
    started[1]!.emit("exit", 0);
    t.mock.timers.tick(5_000);
    assert.equal(started.length, 2);
  });
});
