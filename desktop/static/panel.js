// The Say it in English panel: draws what the app says it is doing, records when told to,
// and sends back the recording, a typed text, or what the person chose. It holds no state
// of its own beyond the recording in progress; the app decides everything else.

const LANGUAGE = { es: "Spanish", pt: "Portuguese", fr: "French", it: "Italian", de: "German", ca: "Catalan", en: "English" };
const LABEL = { organized: "Organized", direct: "Direct", corrected: "Corrected", polished: "Polished", rough: "Rough" };
const PAIR = { translate: ["organized", "direct"], check: ["corrected", "polished"] };

const card = document.getElementById("card");
let current = null;
let ticking = null;

// ── Drawing ───────────────────────────────────────────────────────────────

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "on") for (const [type, handler] of Object.entries(value)) node.addEventListener(type, handler);
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  node.append(...children.filter((child) => child !== null && child !== undefined));
  return node;
}

function clock(ms) {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function button(label, onClick, extra = {}) {
  return el("button", { type: "button", on: { click: onClick }, text: label, ...extra });
}

function listening(view) {
  const bars = el("span", { class: "bars", "aria-hidden": "true" }, ...Array.from({ length: 10 }, () => el("i")));
  const time = el("span", { class: "time", text: clock(Date.now() - view.since) });
  ticking = setInterval(() => {
    time.textContent = clock(Date.now() - view.since);
    const levels = meterLevels();
    bars.querySelectorAll("i").forEach((bar, i) => (bar.style.height = `${Math.round(20 + 80 * (levels[i] ?? 0))}%`));
  }, 100);
  return [
    el(
      "div",
      { class: "listening" },
      el("span", { class: "rec", "aria-hidden": "true" }),
      bars,
      time,
      el("span", { class: "hint", text: view.handsFree ? "Tap fn, or Done, to finish · esc to cancel" : "Release fn to finish · esc to cancel" }),
      view.handsFree ? button("Done", () => window.panel.act("done"), { class: "done" }) : null,
    ),
  ];
}

function typing() {
  const box = el("textarea", {
    "aria-label": "What to say in English",
    placeholder: "Type in your language, or English to check it",
    on: {
      keydown: (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          window.panel.sendText(box.value);
        } else if (event.key === "Escape") {
          window.panel.act("dismiss");
        }
      },
    },
  });
  setTimeout(() => box.focus(), 0);
  return [
    el("p", { class: "mode", text: "Say it in English" }),
    box,
    el(
      "div",
      { class: "row acts" },
      button("Speak instead", () => window.panel.act("speak")),
      el("span", { class: "hint", text: "Enter for the English · shift-Enter for a new line · esc to close" }),
    ),
  ];
}

function working(view) {
  const what = view.via === "voice" ? "Hearing what you said, then writing the English…" : view.via === "copied" ? "Writing the English for what you copied…" : "Writing the English…";
  return [el("p", { class: "step", text: what }), el("div", { class: "prog" }), el("p", { class: "hint", text: "esc to cancel" })];
}

function result(view) {
  const { capture, shown, editing } = view;
  const check = capture.mode === "check";
  const own = LANGUAGE[capture.source_language] ?? "your language";
  const text = capture.versions[shown] ?? capture.text;
  const dropped = capture.dropped[shown] ?? [];

  const seg = el(
    "div",
    { class: "seg", role: "group", "aria-label": "Version" },
    ...PAIR[capture.mode].map((version) =>
      button(LABEL[version], () => window.panel.choose({ version }), { class: version === shown ? "on" : "", "aria-pressed": String(version === shown) }),
    ),
  );
  const top = el(
    "div",
    { class: "row" },
    el("span", { class: "mode", text: `${check ? "Your English, checked" : `${own} → English`}${capture.app ? ` · ${capture.app}` : ""}` }),
    seg,
    el("span", { class: "ok", text: "✓ Copied · ⌘V to paste" }),
  );
  const english = el("div", { class: "en", text });
  if (editing) {
    english.setAttribute("contenteditable", "true");
    setTimeout(() => english.focus(), 0);
    english.addEventListener("keydown", (event) => {
      if (event.key === "Escape") window.panel.act("dismiss");
    });
  }
  const fixes =
    check && shown === "corrected" && capture.fixes.length > 0
      ? el(
          "ol",
          { class: "fixes", "aria-label": "Fixes" },
          ...capture.fixes.map((fix) => el("li", {}, el("s", { text: fix.original }), el("b", { text: fix.correction }), el("span", { class: "why", text: fix.label }))),
        )
      : null;
  const keep = dropped.length
    ? el("span", { class: "warn", text: `Not found in this version: ${dropped.join(", ")}` })
    : el("span", { class: "keep", text: "✓ Names and numbers kept" });
  const saved = capture.saved ? el("span", { text: "Saved to Notebook" }) : el("span", { class: "unsaved", text: "Not saved: saving is paused" });

  return [
    top,
    ...capture.notes.map((note) => el("p", { class: "warn", text: note })),
    english,
    fixes,
    el("p", { class: "said", text: `${capture.via === "voice" ? "You said" : capture.via === "copied" ? "You copied" : "You typed"}: «${capture.source_text}»` }),
    el("div", { class: "row foot" }, keep, saved),
    el(
      "div",
      { class: "acts" },
      button("Copy again", () => window.panel.choose({ version: shown, again: true })),
      editing
        ? button("Copy my edit", () => window.panel.choose({ edited: english.innerText }), { class: "pri" })
        : button("Edit", () => window.panel.act("edit")),
      capture.saved ? button("Open in Notebook", () => window.panel.act("open")) : null,
      button(check ? `It was ${own}` : "It was English", () => window.panel.act("switch")),
      el("span", { class: "hint", text: "⌘V to paste · esc to close" }),
    ),
  ];
}

function problem(view) {
  return [el("h1", { text: view.title }), el("p", { class: "foot", text: view.body })];
}

function render(view) {
  current = view;
  clearInterval(ticking);
  ticking = null;
  const parts =
    view.kind === "listening" ? listening(view)
    : view.kind === "typing" ? typing()
    : view.kind === "working" ? working(view)
    : view.kind === "result" ? result(view)
    : problem(view);
  card.replaceChildren(...parts.filter(Boolean));
  requestAnimationFrame(() => window.panel.resize(card.getBoundingClientRect().height));
}

// ── Recording ─────────────────────────────────────────────────────────────

let stream = null;
let recorder = null;
let chunks = [];
let startedAt = 0;
let analyser = null;
let audioContext = null;
let pending = null;

function meterLevels() {
  if (!analyser) return [];
  const data = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(data);
  const band = Math.floor(data.length / 10);
  return Array.from({ length: 10 }, (_, i) => Math.min(1, (data.slice(i * band, (i + 1) * band).reduce((a, b) => a + b, 0) / band) / 160));
}

function release() {
  stream?.getTracks().forEach((track) => track.stop());
  void audioContext?.close();
  stream = recorder = analyser = audioContext = null;
  chunks = [];
}

async function start() {
  if (stream || pending) return;
  pending = "recording";
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    stream = null;
  }
  const then = pending;
  pending = null;
  if (!stream) {
    if (then === "stop") window.panel.sendAudio(new Uint8Array(0), "audio/webm", 0);
    return;
  }
  const type = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
  recorder = new MediaRecorder(stream, type ? { mimeType: type } : {});
  chunks = [];
  recorder.ondataavailable = (event) => event.data.size && chunks.push(event.data);
  startedAt = performance.now();
  recorder.start(250);
  audioContext = new AudioContext();
  analyser = audioContext.createAnalyser();
  audioContext.createMediaStreamSource(stream).connect(analyser);
  if (then === "stop") stop();
  else if (then === "discard") release();
}

function stop() {
  if (pending) {
    pending = "stop";
    return;
  }
  if (!recorder) {
    window.panel.sendAudio(new Uint8Array(0), "audio/webm", 0);
    return;
  }
  const active = recorder;
  const durationMs = Math.round(performance.now() - startedAt);
  active.onstop = async () => {
    const blob = new Blob(chunks, { type: active.mimeType || "audio/webm" });
    const bytes = new Uint8Array(await blob.arrayBuffer());
    release();
    window.panel.sendAudio(bytes, blob.type, durationMs);
  };
  active.stop();
}

function discard() {
  if (pending) {
    pending = "discard";
    return;
  }
  if (recorder) {
    recorder.onstop = () => release();
    recorder.stop();
  } else {
    release();
  }
}

window.panel.onState(render);
window.panel.onRecord((command) => {
  if (command === "start") void start();
  else if (command === "stop") stop();
  else if (command === "discard") discard();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && current && current.kind !== "typing") window.panel.act("dismiss");
});
