// Drives the app's window over the DevTools protocol, as a person would: register on the
// first launch's page, hold the button for one conversation turn and wait for the reply to
// play, then read a passage aloud and wait for its score. One JSON line per step; exits 1
// on the first step that does not happen.
//   node smoke.mjs <devtools port> [hold ms]

const [port = "9333", holdArg = "6500"] = process.argv.slice(2);
const HOLD_MS = Number(holdArg);
const ORIGIN = "http://127.0.0.1:3013";
const API = "http://127.0.0.1:8012";
const t0 = Date.now();
const out = (step, data = {}) => console.log(JSON.stringify({ t: Date.now() - t0, step, ...data }));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function pageTarget(limitMs) {
  const deadline = Date.now() + limitMs;
  while (Date.now() < deadline) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = list.find((t) => t.type === "page" && t.url.startsWith(ORIGIN));
      if (page) return page.webSocketDebuggerUrl;
    } catch {
      // The app is still starting.
    }
    await sleep(250);
  }
  throw new Error("the main window never opened");
}

// A first launch downloads the weights unless they were cloned in: up to ten minutes.
const ws = new WebSocket(await pageTarget(600_000));
await new Promise((resolve) => ws.addEventListener("open", resolve, { once: true }));
let nextId = 0;
const pending = new Map();
const listeners = [];
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(JSON.stringify(msg.error)));
    else resolve(msg.result);
  } else if (msg.method) {
    for (const listener of listeners) listener(msg);
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
async function until(label, expression, limitMs = 30_000) {
  const start = Date.now();
  for (;;) {
    const value = await evaluate(expression).catch(() => null);
    if (value) return value;
    if (Date.now() - start > limitMs) throw new Error(`timed out waiting for ${label}`);
    await sleep(100);
  }
}

// What the page asked for and what failed, for the summary.
const requests = new Map();
const turnResponses = [];
const failures = [];
listeners.push((msg) => {
  const p = msg.params;
  if (msg.method === "Network.requestWillBeSent") requests.set(p.requestId, p.request);
  if (msg.method === "Network.responseReceived") {
    const request = requests.get(p.requestId) ?? {};
    if (/\/sessions\/[^/]+\/turns$/.test(p.response.url) && request.method === "POST") {
      turnResponses.push({ requestId: p.requestId, status: p.response.status, at: Date.now() });
    }
    if (p.response.status >= 500) failures.push({ url: p.response.url, status: p.response.status });
  }
  if (msg.method === "Network.loadingFailed" && !p.canceled) {
    failures.push({ url: requests.get(p.requestId)?.url, error: p.errorText });
  }
});
await send("Network.enable");
await send("Page.enable");
await send("Runtime.enable");

// A server-rendered button is in the page before React has hydrated it, and a press that
// arrives first does nothing, so an element is pressed only once it carries React's props.
async function boxOf(selector) {
  return until(`the box of ${selector}`, `(() => { const el = ${selector};
    if (!el || !Object.keys(el).some((k) => k.startsWith("__reactProps$"))) return null;
    el.scrollIntoView({ block: "center" }); const r = el.getBoundingClientRect();
    return r.width ? { x: r.x + r.width / 2, y: r.y + r.height / 2 } : null; })()`);
}
async function click(selector) {
  const { x, y } = await boxOf(selector);
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
}
async function typeInto(selector, text) {
  await evaluate(`(${selector}).focus()`);
  await send("Input.insertText", { text });
}
async function hold(selector, ms) {
  const { x, y } = await boxOf(selector);
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: 1 });
  await sleep(ms);
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", buttons: 0, clickCount: 1 });
  return Date.now();
}
const byText = (tag, text) =>
  `[...document.querySelectorAll("${tag}")].find((el) => el.textContent.trim().startsWith(${JSON.stringify(text)}) && !el.disabled)`;

try {
  // 1. The first launch opens on registration.
  await until("the registration page", `location.pathname === "/register" && !!document.querySelector("#email")`, 60_000);
  const email = `smoke-${Date.now()}@example.com`;
  await typeInto(`document.querySelector("#email")`, email);
  await typeInto(`document.querySelector("#password")`, "smoke-test-password");
  await click(byText("button", "Create account"));
  await until("the scenarios page", `location.pathname === "/scenarios"`);
  out("registered", { email });

  // 2. One conversation turn, heard back.
  await send("Page.navigate", { url: `${ORIGIN}/scenarios/job-interview-backend` });
  await until("the scenario page", `location.pathname === "/scenarios/job-interview-backend" && document.readyState === "complete"`);
  await click(byText("button", "Start"));
  await until("the session page", `/^\\/sessions\\/[0-9a-f-]+$/.test(location.pathname)`, 60_000);
  const audiosBefore = await evaluate(`document.querySelectorAll("audio").length`);
  const released = await hold(`document.querySelector('button[aria-label="Hold to speak"]')`, HOLD_MS);
  for (let i = 0; i < 1200 && turnResponses.length === 0; i++) await sleep(50);
  const turn = turnResponses[0];
  if (!turn || turn.status >= 300) throw new Error(`the turn answered ${turn?.status ?? "nothing"}`);
  const body = JSON.parse((await send("Network.getResponseBody", { requestId: turn.requestId })).body);
  if (!body.user_turn?.transcript || !body.reply_turn?.transcript) throw new Error("the turn came back without a transcript or a reply");
  out("turn answered", {
    afterReleaseMs: turn.at - released,
    said: body.user_turn.transcript,
    reply: body.reply_turn.transcript,
  });
  await until(
    "the reply to play",
    `(() => { const a = [...document.querySelectorAll("audio")]; const last = a[a.length - 1];
       return a.length > ${audiosBefore} && last && (last.currentTime > 1 || last.ended); })()`,
  );
  out("reply played");

  // 3. One read-aloud, scored.
  await send("Page.navigate", { url: `${ORIGIN}/read` });
  await until("the passages", `document.readyState === "complete" && !!document.querySelector('a[href^="/read/"]')`);
  const passage = await evaluate(`document.querySelector('a[href^="/read/"]').getAttribute("href")`);
  await send("Page.navigate", { url: `${ORIGIN}${passage}` });
  await until("the passage page", `location.pathname === ${JSON.stringify(passage)} && document.readyState === "complete"`);
  await hold(`document.querySelector('button[aria-pressed]')`, HOLD_MS);
  const attempt = await until(
    "the reading to be scored",
    `(async () => { const r = await fetch("${API}/attempts?limit=1", { credentials: "include" }).catch(() => null);
       if (!r || !r.ok) return null; const body = await r.json();
       const items = Array.isArray(body) ? body : body.items; const a = items?.[0];
       return a && (a.status === "scored" || a.status === "failed") ? a : null; })()`,
    120_000,
  );
  if (attempt.status !== "scored") throw new Error(`the reading ended ${attempt.status}`);
  out("reading scored", { passage, id: attempt.id, pronunciation: attempt.pronunciation ?? null });

  if (failures.length > 0) throw new Error(`requests failed: ${JSON.stringify(failures.slice(0, 5))}`);
  out("passed");
  ws.close();
} catch (error) {
  out("failed", { error: String(error), failures: failures.slice(0, 5) });
  ws.close();
  process.exit(1);
}
