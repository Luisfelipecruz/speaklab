// Say it in English on the built app, as a person uses it: fn held over TextEdit while the
// clip plays, fn released, and the English on the clipboard. The account is made in the
// main window over the DevTools protocol; fn is played through the pipe the app reads in
// place of its helper; the times are the app's own trace, release to clipboard. Warm
// first, a dictation that is not counted loading the model; then one after Ollama has
// unloaded it. One JSON line per step; exits 1 when a dictation does not reach the
// clipboard or the app in front loses focus.
//   node say.mjs <devtools port> <keys pipe> <trace file> <clip seconds> [dictations]

import { execFileSync } from "node:child_process";
import { openSync, readFileSync, writeFileSync, writeSync } from "node:fs";
import { dirname, join } from "node:path";

const [port, keysPipe, traceFile, clipArg, countArg = "20"] = process.argv.slice(2);
const CLIP_MS = Math.round(Number(clipArg) * 1000);
const COUNT = Number(countArg);
const FULL = process.env.FULL === "1";
const FRONT = "TextEdit";
const ORIGIN = "http://127.0.0.1:3013";
const API = "http://127.0.0.1:8012";
const OLLAMA = process.env.OLLAMA_URL ?? "http://127.0.0.1:11434";
// Past the 180 ms that makes a press a hold, and past the clip, which starts with the
// microphone on fn down.
const HOLD_MS = CLIP_MS + 600;
const BAR_P95_MS = 3000;
const t0 = Date.now();
const out = (step, data = {}) => console.log(JSON.stringify({ t: Date.now() - t0, step, ...data }));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const run = (file, args) => execFileSync(file, args, { encoding: "utf8" }).trim();
const osa = (...lines) => run("/usr/bin/osascript", lines.flatMap((line) => ["-e", line]));
// Through Launch Services rather than Apple Events, so no Automation prompt is raised.
const bringForward = (...files) => run("/usr/bin/open", ["-a", FRONT, ...files]);

function front() {
  const asn = run("/usr/bin/lsappinfo", ["front"]);
  return /"LSDisplayName"="([^"]*)"/.exec(run("/usr/bin/lsappinfo", ["info", "-only", "name", asn]))?.[1] ?? null;
}

function trace() {
  try {
    return readFileSync(traceFile, "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line));
  } catch {
    return [];
  }
}

async function until(label, check, limitMs = 30_000) {
  const start = Date.now();
  for (;;) {
    const value = await check();
    if (value) return value;
    if (Date.now() - start > limitMs) throw new Error(`timed out waiting for ${label}`);
    await sleep(50);
  }
}

// ── The main window, for an account ─────────────────────────────────────────

async function pageTarget(limitMs) {
  return until(
    "the main window",
    async () => {
      try {
        const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
        return list.find((t) => t.type === "page" && t.url.startsWith(ORIGIN))?.webSocketDebuggerUrl;
      } catch {
        return null;
      }
    },
    limitMs,
  );
}

// A first launch downloads the weights unless they were cloned in: up to ten minutes.
const ws = new WebSocket(await pageTarget(600_000));
await new Promise((resolve) => ws.addEventListener("open", resolve, { once: true }));
let nextId = 0;
const pending = new Map();
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(JSON.stringify(msg.error)));
    else resolve(msg.result);
  }
});
const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
const evaluate = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));
  return r.result.value;
};
const page = (label, expression, limitMs) => until(label, () => evaluate(expression).catch(() => null), limitMs);

// ── The key ─────────────────────────────────────────────────────────────────

let keys = null;
function key(line) {
  writeSync(keys, `${JSON.stringify(line)}\n`);
}

/** One dictation: TextEdit in front, fn held over the clip, released, and what followed. */
async function dictate(label) {
  bringForward();
  await until(`${FRONT} in front`, () => front() === FRONT, 10_000);
  const sentinel = `speaklab-say-${Date.now()}`;
  execFileSync("/usr/bin/pbcopy", { input: sentinel });
  const seen = trace().length;
  key({ t: "down", app: FRONT });
  await sleep(HOLD_MS);
  key({ t: "up" });
  const copied = await until("the English on the clipboard", () => trace().slice(seen).find((e) => e.event === "copied"), 120_000);
  const released = trace().slice(seen).find((e) => e.event === "released");
  const clipboard = run("/usr/bin/pbpaste", []);
  const row = {
    label,
    releaseToClipboardMs: copied.at - released.at,
    version: copied.version,
    front: front(),
    clipboardChanged: clipboard !== sentinel && clipboard.length > 0,
  };
  out("dictation", row);
  // The result shows for 8 s; the next fn replaces it, but a pause keeps one from
  // running into the next.
  await sleep(1500);
  return row;
}

function p95(values) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil(0.95 * sorted.length) - 1)];
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

try {
  await page("the registration page", `location.pathname === "/register" && !!document.querySelector("#email")`, 60_000);
  const email = `say-${Date.now()}@example.com`;
  const registered = await evaluate(`fetch("${API}/auth/register", {
    method: "POST", credentials: "include", headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: ${JSON.stringify(email)}, password: "say-test-password", native_language: "es" }),
  }).then((r) => r.status)`);
  if (registered >= 300) throw new Error(`registration answered ${registered}`);
  out("registered", { email });

  const note = join(dirname(traceFile), "note.txt");
  writeFileSync(note, "");
  bringForward(note);
  if (FULL) {
    osa(`tell application "System Events" to tell process "${FRONT}" to set value of attribute "AXFullScreen" of window 1 to true`);
    await sleep(1500);
    out("full screen", { app: FRONT });
  }
  // Opening the pipe waits for the app to have it open for reading: its key helper.
  keys = openSync(keysPipe, "w");
  out("key pipe open");

  await dictate("loading the model");
  const warm = [];
  for (let i = 1; i <= COUNT; i++) warm.push(await dictate(`warm ${i}`));

  await fetch(`${OLLAMA}/api/generate`, { method: "POST", body: JSON.stringify({ model: process.env.OLLAMA_MODEL ?? "gemma4:e4b", keep_alive: 0 }) });
  await sleep(2000);
  const cold = await dictate("after Ollama unloaded the model");

  const times = warm.map((row) => row.releaseToClipboardMs);
  const all = [...warm, cold];
  const kept = all.filter((row) => row.front === FRONT).length;
  const reached = all.filter((row) => row.clipboardChanged).length;
  out("summary", {
    dictations: warm.length,
    warmMedianMs: median(times),
    warmP95Ms: p95(times),
    warmMaxMs: Math.max(...times),
    coldMs: cold.releaseToClipboardMs,
    frontKept: `${kept} of ${all.length}`,
    clipboardReached: `${reached} of ${all.length}`,
    fullScreen: FULL,
    d1: p95(times) <= BAR_P95_MS ? "met" : "not met",
  });
  ws.close();
  if (kept !== all.length || reached !== all.length) process.exit(1);
} catch (error) {
  out("failed", { error: String(error) });
  ws.close();
  process.exit(1);
}
