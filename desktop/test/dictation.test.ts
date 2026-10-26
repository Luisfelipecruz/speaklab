import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  type Capture,
  type CaptureRequest,
  Dictation,
  LINGER_MS,
  LONGEST_MS,
  type PanelView,
  RESULT_MAX_MS,
  RESULT_MS,
  readingMs,
  type SayApi,
  SayApiError,
  SHORTEST_MS,
  type Version,
} from "../src/dictation.ts";
import { DEFAULTS, type SaySettings } from "../src/say-settings.ts";
import { fakeTimers } from "./timers.ts";

const SAID = "mañana te mando el informe";
const ENGLISH = "I will send you the report tomorrow.";
const sound = new Uint8Array([1, 2, 3, 4]);

function capture(over: Partial<Capture> = {}): Capture {
  return {
    id: 41,
    saved: true,
    mode: "translate",
    via: "voice",
    source_language: "es",
    source_text: SAID,
    app: "Mail",
    chosen: "organized",
    text: ENGLISH,
    versions: { organized: ENGLISH, direct: null },
    dropped: { organized: [] },
    fixes: [],
    notes: [],
    ...over,
  };
}

/** A promise the test settles when it chooses. */
function later<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

class FakeApi implements SayApi {
  warmed = 0;
  requests: CaptureRequest[] = [];
  asked: [number, Version][] = [];
  removed: number[] = [];
  answer: (request: CaptureRequest) => Promise<Capture> = async (request) => capture({ via: request.via });
  written: (id: number, version: Version) => Promise<Capture> = async () => capture();

  async warm(): Promise<void> {
    this.warmed++;
  }

  capture(request: CaptureRequest): Promise<Capture> {
    this.requests.push(request);
    return this.answer(request);
  }

  version(id: number, version: Version): Promise<Capture> {
    this.asked.push([id, version]);
    return this.written(id, version);
  }

  async remove(id: number): Promise<void> {
    this.removed.push(id);
  }
}

function rig(options: { settings?: Partial<SaySettings>; copying?: () => Promise<void> } = {}) {
  const log: string[] = [];
  const views: PanelView[] = [];
  const traced: Record<string, unknown>[] = [];
  const api = new FakeApi();
  const timers = fakeTimers();
  const dictation = new Dictation({
    api,
    panel: {
      show: (view, focus) => {
        views.push(view);
        log.push(`show ${view.kind}${focus ? " focused" : ""}`);
      },
      hide: () => log.push("hide"),
      record: (command) => log.push(`record ${command}`),
    },
    writeClipboard: async (text) => {
      await options.copying?.();
      log.push(`copy ${text}`);
    },
    settings: () => ({ ...DEFAULTS, ...options.settings }),
    signIn: () => log.push("sign in"),
    openNotebook: (id) => log.push(`open ${id}`),
    giveFocusBack: () => log.push("focus back"),
    stoppedListening: () => log.push("stopped listening"),
    now: () => 1_000,
    timers,
    trace: (event, fields = {}) => traced.push({ event, ...fields }),
  });
  return { dictation, log, views, traced, api, timers };
}

type Rig = ReturnType<typeof rig>;

function result(r: Rig): Extract<PanelView, { kind: "result" }> {
  const view = r.views.at(-1);
  assert.ok(view?.kind === "result", `the panel shows ${view?.kind}`);
  return view;
}

function problem(r: Rig): Extract<PanelView, { kind: "problem" }> {
  const view = r.views.at(-1);
  assert.ok(view?.kind === "problem", `the panel shows ${view?.kind}`);
  return view;
}

/** fn held, something said, fn released. */
async function said(r: Rig, durationMs = 2_000): Promise<void> {
  r.dictation.arm("Mail");
  r.dictation.hold();
  r.dictation.finish();
  await r.dictation.audio(sound, "audio/webm", durationMs);
}

describe("saying it", () => {
  it("sends the recording, copies the English, and goes after 8 s", async () => {
    const r = rig();
    await said(r);

    assert.deepEqual(r.log, ["record start", "show listening", "record stop", "show working", `copy ${ENGLISH}`, "show result"]);
    assert.equal(r.api.warmed, 1);
    assert.deepEqual(r.api.requests, [
      { audio: { bytes: sound, mimeType: "audio/webm" }, via: "voice", app: "Mail", mode: "auto", versions: ["organized", "corrected"], save: true },
    ]);
    assert.equal(result(r).shown, "organized");

    r.timers.advance(RESULT_MS - 1);
    assert.equal(r.dictation.state, "result");
    r.timers.advance(1);
    assert.equal(r.dictation.state, "idle");
    assert.equal(r.log.at(-1), "hide");
  });

  it("traces times and versions, never words", async () => {
    const r = rig();
    await said(r);

    assert.deepEqual(
      r.traced.map((entry) => entry.event),
      ["down", "released", "copied"],
    );
    const traced = JSON.stringify(r.traced);
    assert.ok(!traced.includes("informe") && !traced.includes("report"), traced);
  });

  it("sends what the settings say: the version from each language, and whether to save", async () => {
    const r = rig({ settings: { fromOwn: "direct", fromEnglish: "polished", save: false } });
    await said(r);

    assert.deepEqual(r.api.requests[0]?.versions, ["direct", "polished"]);
    assert.equal(r.api.requests[0]?.save, false);
  });

  it("drops a recording under 0.4 s without sending it", async () => {
    const r = rig();
    await said(r, SHORTEST_MS - 1);

    assert.equal(r.api.requests.length, 0);
    assert.equal(r.dictation.state, "idle");
    assert.equal(r.log.at(-1), "hide");
  });

  it("says so when the microphone gave nothing at all", async () => {
    const r = rig();
    r.dictation.arm("Mail");
    r.dictation.hold();
    r.dictation.finish();
    await r.dictation.audio(new Uint8Array(0), "audio/webm", 0);

    assert.equal(problem(r).title, "The microphone did not open");
    assert.equal(r.api.requests.length, 0);
  });

  it("discards what a tap that came to nothing heard", () => {
    const r = rig();
    r.dictation.arm("Mail");
    r.dictation.cancel();

    assert.deepEqual(r.log, ["record start", "record discard", "hide"]);
    assert.equal(r.dictation.state, "idle");
  });

  it("stops listening by itself at two minutes, and sends what it heard", () => {
    const r = rig();
    r.dictation.arm("Mail");
    r.dictation.handsFree();
    r.timers.advance(LONGEST_MS);

    assert.deepEqual(r.log.slice(-3), ["stopped listening", "record stop", "show working"]);
    assert.equal(r.dictation.state, "working");
  });
});

describe("when it cannot be done", () => {
  it("shows the API's own words for what it could not use: silence", async () => {
    const r = rig();
    r.api.answer = async () => {
      throw new SayApiError("Nothing was heard in that recording.", 422);
    };
    await said(r);

    assert.deepEqual(problem(r), { kind: "problem", title: "SpeakLab could not use that", body: "Nothing was heard in that recording." });
    assert.ok(!r.log.some((line) => line.startsWith("copy")));
    r.timers.advance(RESULT_MS);
    assert.equal(r.dictation.state, "idle");
  });

  it("opens the sign-in page on 401, and says nothing was saved", async () => {
    const r = rig();
    r.api.answer = async () => {
      throw new SayApiError("Not signed in", 401);
    };
    await said(r);

    assert.ok(r.log.includes("sign in"));
    assert.equal(problem(r).title, "Sign in to SpeakLab first");
    assert.match(problem(r).body, /Nothing was saved/);
  });

  it("passes on a 503 as the API put it, and copies nothing", async () => {
    const r = rig();
    const detail = "The recogniser for your own language is not answering. Nothing was saved.";
    r.api.answer = async () => {
      throw new SayApiError(detail, 503);
    };
    await said(r);

    assert.deepEqual(problem(r), { kind: "problem", title: "It could not be done", body: detail });
    assert.ok(!r.log.some((line) => line.startsWith("copy")));
  });

  it("says SpeakLab is not answering when the request never reached it", async () => {
    const r = rig();
    r.api.answer = async () => {
      throw new SayApiError("connect ECONNREFUSED 127.0.0.1:8110", 0);
    };
    await said(r);

    assert.equal(problem(r).title, "SpeakLab is not answering");
  });

  it("copies the recogniser's rough English when the model is down, with the note", async () => {
    const r = rig();
    const rough = "Tomorrow I send you the report.";
    const note = "The language model is not answering: this is the recogniser's own English, rougher.";
    r.api.answer = async () =>
      capture({ chosen: "rough", text: rough, versions: { rough, organized: null, direct: null }, dropped: {}, notes: [note] });
    await said(r);

    assert.ok(r.log.includes(`copy ${rough}`));
    assert.equal(result(r).shown, "rough");
    assert.deepEqual(result(r).capture.notes, [note]);
  });
});

describe("the clipboard", () => {
  it("has the English on it before the panel says it is copied", async () => {
    const copying = later<void>();
    const r = rig({ copying: () => copying.promise });
    r.dictation.arm("Mail");
    r.dictation.hold();
    r.dictation.finish();
    const sending = r.dictation.audio(sound, "audio/webm", 2_000);
    await new Promise((resolve) => setImmediate(resolve));

    assert.equal(r.dictation.state, "working");
    assert.equal(r.views.at(-1)?.kind, "working");
    copying.resolve();
    await sending;
    assert.deepEqual(r.log.slice(-2), [`copy ${ENGLISH}`, "show result"]);
  });

  it("that cannot be written is a problem, said in its own words", async () => {
    const r = rig({
      copying: async () => {
        throw new Error("The pasteboard is not available.");
      },
    });
    await said(r);

    assert.deepEqual(problem(r), { kind: "problem", title: "It could not be copied", body: "The pasteboard is not available." });
  });

  it("is not followed by the panel when Esc came while it was being written", async () => {
    const copying = later<void>();
    const r = rig({ copying: () => copying.promise });
    r.dictation.arm("Mail");
    r.dictation.hold();
    r.dictation.finish();
    const sending = r.dictation.audio(sound, "audio/webm", 2_000);
    await new Promise((resolve) => setImmediate(resolve));
    r.dictation.dismiss();
    copying.resolve();
    await sending;

    assert.equal(r.dictation.state, "idle");
    assert.equal(r.log.at(-1), `copy ${ENGLISH}`);
    assert.ok(!r.log.slice(r.log.indexOf("hide")).includes("show result"));
  });
});

describe("Esc", () => {
  it("while working abandons it: the answer is not shown, and what it saved is deleted", async () => {
    const r = rig();
    const answer = later<Capture>();
    r.api.answer = () => answer.promise;
    r.dictation.arm("Mail");
    r.dictation.hold();
    r.dictation.finish();
    const sending = r.dictation.audio(sound, "audio/webm", 2_000);

    r.dictation.dismiss();
    assert.equal(r.dictation.state, "idle");
    answer.resolve(capture({ id: 77 }));
    await sending;

    assert.deepEqual(r.api.removed, [77]);
    assert.ok(!r.log.some((line) => line.startsWith("copy")));
    assert.equal(r.log.at(-1), "hide");
  });

  it("while working leaves nothing to show when the abandoned request fails", async () => {
    const r = rig();
    const answer = later<Capture>();
    r.api.answer = () => answer.promise;
    r.dictation.typing("Notes");
    const sending = r.dictation.text("hola");
    r.dictation.dismiss();
    answer.reject(new SayApiError("Not signed in", 401));
    await sending;

    assert.ok(!r.log.includes("sign in"));
    assert.equal(r.dictation.state, "idle");
  });

  it("while listening discards the recording", () => {
    const r = rig();
    r.dictation.arm("Mail");
    r.dictation.hold();
    r.dictation.dismiss();

    assert.deepEqual(r.log.slice(-2), ["record discard", "hide"]);
  });
});

describe("typing", () => {
  it("opens the panel focused, and gives focus back before the work is shown", async () => {
    const r = rig();
    r.dictation.typing("Notes");
    assert.deepEqual(r.log, ["show typing focused"]);
    assert.equal(r.api.warmed, 1);

    await r.dictation.text("necesito el informe para el viernes");

    assert.deepEqual(r.log.slice(1, 3), ["focus back", "show working"]);
    assert.deepEqual(r.api.requests, [
      { text: "necesito el informe para el viernes", via: "typed", app: "Notes", mode: "auto", versions: ["organized", "corrected"], save: true },
    ]);
    assert.equal(r.dictation.state, "result");
  });

  it("closes without sending on Esc or an empty box, and gives focus back", async () => {
    for (const end of ["escape", "empty"] as const) {
      const r = rig();
      r.dictation.typing("Notes");
      if (end === "escape") r.dictation.dismiss();
      else await r.dictation.text("  \n ");

      assert.deepEqual(r.log, ["show typing focused", "focus back", "hide"], end);
      assert.equal(r.api.requests.length, 0);
    }
  });

  it("is left alone by fn: a shortcut such as fn-← while typing is the box's", () => {
    const r = rig();
    r.dictation.typing("Notes");
    r.dictation.arm("Notes");
    r.dictation.cancel();
    r.dictation.typing("Notes");

    assert.equal(r.dictation.state, "typing");
    assert.deepEqual(r.log, ["show typing focused"]);
  });

  it("speaks instead: hands-free from the panel, with focus given back first", () => {
    const r = rig();
    r.dictation.typing("Notes");
    r.dictation.speakInstead();

    assert.deepEqual(r.log, ["show typing focused", "record start", "focus back", "show listening"]);
    assert.deepEqual(r.views.at(-1), { kind: "listening", handsFree: true, since: 1_000 });
    r.dictation.finish();
    assert.equal(r.dictation.state, "working");
  });

  it("drops a recording in progress when it opens", () => {
    const r = rig();
    r.dictation.arm("Mail");
    r.dictation.hold();
    r.dictation.typing("Mail");

    assert.ok(r.log.includes("record discard"));
    assert.equal(r.dictation.state, "typing");
  });
});

describe("what was copied", () => {
  it("is translated or checked, and the English put back on the clipboard", async () => {
    const r = rig();
    await r.dictation.copied("Safari", "quedamos el lunes a las 10");

    assert.deepEqual(r.api.requests, [
      { text: "quedamos el lunes a las 10", via: "copied", app: "Safari", mode: "auto", versions: ["organized", "corrected"], save: true },
    ]);
    assert.ok(r.log.includes(`copy ${ENGLISH}`));
  });

  it("is a problem when there is nothing on the clipboard", async () => {
    const r = rig();
    await r.dictation.copied("Safari", " ");

    assert.equal(problem(r).title, "Nothing to translate");
    assert.equal(r.api.requests.length, 0);
  });
});

describe("the result", () => {
  it("is replaced by the next fn, which stops its timer; work in flight is never interrupted", async () => {
    const r = rig();
    await said(r);
    r.dictation.arm("Mail");
    assert.equal(r.dictation.state, "armed");
    r.timers.advance(RESULT_MS);
    assert.equal(r.dictation.state, "armed");

    const answer = later<Capture>();
    r.api.answer = () => answer.promise;
    r.dictation.hold();
    r.dictation.finish();
    const sending = r.dictation.audio(sound, "audio/webm", 2_000);
    const before = r.log.length;
    r.dictation.arm("Mail");
    r.dictation.cancel();
    r.dictation.typing("Mail");
    assert.equal(r.log.length, before);
    answer.resolve(capture());
    await sending;
    assert.equal(r.dictation.state, "result");
  });

  it("copies a version written already at once, and asks for one not written yet", async () => {
    const r = rig();
    await said(r);
    const direct = "Tomorrow I send you the report.";
    r.api.written = async () => capture({ versions: { direct }, dropped: { direct: [] } });

    await r.dictation.choose("direct");
    assert.deepEqual(r.api.asked, [[41, "direct"]]);
    assert.deepEqual(r.log.slice(-2), [`copy ${direct}`, "show result"]);
    assert.deepEqual(result(r).capture.versions, { organized: ENGLISH, direct });

    await r.dictation.choose("organized");
    assert.equal(r.api.asked.length, 1);
    assert.equal(r.log.at(-2), `copy ${ENGLISH}`);
  });

  it("is not closed by its own timer while another version is being written", async () => {
    const r = rig();
    await said(r);
    const written = later<Capture>();
    r.api.written = () => written.promise;
    r.timers.advance(RESULT_MS - 100);

    const choosing = r.dictation.choose("direct");
    r.timers.advance(200);
    assert.equal(r.dictation.state, "working");
    written.resolve(capture({ versions: { direct: "Tomorrow I send you the report." } }));
    await choosing;

    assert.equal(r.dictation.state, "result");
    assert.equal(result(r).shown, "direct");
  });

  it("writes another version of an unsaved capture without saving it", async () => {
    const r = rig({ settings: { save: false } });
    r.api.answer = async (request) =>
      request.versions.length === 1
        ? capture({ id: null, saved: false, versions: { direct: "Tomorrow I send you the report." } })
        : capture({ id: null, saved: false });
    await said(r);
    await r.dictation.choose("direct");

    assert.deepEqual(r.api.requests[1], { text: SAID, via: "voice", app: "Mail", mode: "translate", versions: ["direct"], save: false });
    assert.equal(r.api.asked.length, 0);
    assert.equal(result(r).shown, "direct");
  });

  it("switches language: the wrong capture deleted, and the same recording sent as the other", async () => {
    const r = rig();
    await said(r);
    await r.dictation.switchLanguage();

    assert.deepEqual(r.api.removed, [41]);
    assert.deepEqual(r.api.requests[1], {
      audio: { bytes: sound, mimeType: "audio/webm" },
      via: "voice",
      app: "Mail",
      mode: "check",
      versions: ["organized", "corrected"],
      save: true,
    });
  });

  it("switches a typed text by sending the text again", async () => {
    const r = rig();
    r.api.answer = async (request) => capture({ via: request.via, source_text: "I has a meeting", mode: "check", chosen: "corrected" });
    r.dictation.typing("Notes");
    await r.dictation.text("I has a meeting");
    await r.dictation.switchLanguage();

    assert.deepEqual(r.api.requests[1], { text: "I has a meeting", via: "typed", app: "Mail", mode: "translate", versions: ["organized", "corrected"], save: true });
  });

  it("is edited in a focused panel that stays past 8 s, and the edit is what gets copied", async () => {
    const r = rig();
    await said(r);
    r.dictation.edit();

    assert.equal(r.log.at(-1), "show result focused");
    assert.equal(result(r).editing, true);
    r.timers.advance(RESULT_MS * 3);
    assert.equal(r.dictation.state, "result");
    r.dictation.arm("Mail");
    assert.equal(r.dictation.state, "result", "fn does not replace a result being edited");

    await r.dictation.edited("I'll send you the report tomorrow.");
    assert.deepEqual(r.log.slice(-3), ["copy I'll send you the report tomorrow.", "focus back", "hide"]);
  });

  it("edits the version shown, not the one first chosen", async () => {
    const r = rig();
    r.api.answer = async () => capture({ versions: { organized: ENGLISH, direct: "Tomorrow I send you the report." } });
    await said(r);
    await r.dictation.choose("direct");
    r.dictation.edit();

    assert.equal(result(r).shown, "direct");
  });

  it("stays long enough to read: 8 s for a line, a third of a second a word for more, 30 s at most", async () => {
    assert.equal(readingMs(ENGLISH), RESULT_MS);
    const long = Array.from({ length: 60 }, (_, i) => `word${i}`).join(" ");
    assert.equal(readingMs(long), 60 * 330);
    assert.equal(readingMs(`${long} ${long} ${long} ${long}`), RESULT_MAX_MS);

    const r = rig();
    r.api.answer = async () => capture({ text: long, versions: { organized: long, direct: null } });
    await said(r);
    r.timers.advance(60 * 330 - 1);
    assert.equal(r.dictation.state, "result");
    r.timers.advance(1);
    assert.equal(r.dictation.state, "idle");
  });

  it("stays while the pointer is over it, and goes a moment after the pointer leaves", async () => {
    const r = rig();
    await said(r);
    r.dictation.hover(true);
    r.timers.advance(RESULT_MAX_MS * 2);
    assert.equal(r.dictation.state, "result");

    r.dictation.hover(false);
    r.timers.advance(LINGER_MS - 1);
    assert.equal(r.dictation.state, "result");
    r.timers.advance(1);
    assert.equal(r.dictation.state, "idle");
  });

  it("is not ended by the pointer leaving while it is being edited", async () => {
    const r = rig();
    await said(r);
    r.dictation.edit();
    r.dictation.hover(false);
    r.timers.advance(LINGER_MS * 5);

    assert.equal(r.dictation.state, "result");
  });

  it("opens its moment in the Notebook once the panel has gone", async () => {
    const r = rig();
    await said(r);
    r.dictation.open();

    assert.deepEqual(r.log.slice(-2), ["hide", "open 41"]);
  });
});
