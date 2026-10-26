// Say it in English, from the key to the clipboard: one state machine.
//
//   idle → armed      fn down: the model warmed, the microphone open
//        → listening  held 180 ms, or two taps: the panel shown
//        → working    released: the recording sent
//        → result     the English on the clipboard, for 8 s or until Esc or the next fn
//   idle → typing     ⌃⌥Space: the panel focused to type in, the model warmed
//        → working    Enter: the text sent, and focus given back to the app in front
//
// Esc closes whatever is showing. Work in flight is abandoned: its answer is never shown,
// and a capture it saved is deleted when it arrives.
//
// It knows nothing of Electron: the panel, the API, the clipboard and the clock are given
// to it, which is what lets the tests run it against fakes. What it traces are times and
// states, never words.

import type { SaySettings } from "./say-settings.ts";
import { realTimers, type Timers } from "./keys.ts";

export type Version = "direct" | "organized" | "corrected" | "polished" | "rough";
export type Via = "voice" | "typed" | "copied";

/** The capture as the API returns it, the part the panel shows. */
export interface Capture {
  id: number | null;
  saved: boolean;
  mode: "translate" | "check";
  via: Via;
  source_language: string;
  source_text: string;
  app: string | null;
  chosen: Version;
  text: string;
  versions: Partial<Record<Version, string | null>>;
  dropped: Partial<Record<Version, string[]>>;
  fixes: { original: string; correction: string; label: string; counted: boolean }[];
  notes: string[];
}

export interface CaptureRequest {
  audio?: { bytes: Uint8Array; mimeType: string };
  text?: string;
  via: Via;
  app: string | null;
  mode: "auto" | "translate" | "check";
  /** One preference per mode: the API uses the one the mode it decides offers. */
  versions: Version[];
  save: boolean;
}

export class SayApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export interface SayApi {
  warm(): Promise<void>;
  capture(request: CaptureRequest): Promise<Capture>;
  version(id: number, version: Version): Promise<Capture>;
  remove(id: number): Promise<void>;
}

export type PanelView =
  | { kind: "listening"; handsFree: boolean; since: number }
  | { kind: "typing" }
  | { kind: "working"; via: Via }
  | { kind: "result"; capture: Capture; shown: Version; editing: boolean }
  | { kind: "problem"; title: string; body: string };

export interface Panel {
  /** Shown over the app in front without taking focus, unless `focus`: typing and editing. */
  show(view: PanelView, focus: boolean): void;
  hide(): void;
  record(command: "start" | "stop" | "discard"): void;
}

export interface Deps {
  api: SayApi;
  panel: Panel;
  /** Resolves once the text is on the clipboard. */
  writeClipboard(text: string): Promise<void>;
  settings(): SaySettings;
  /** The main window on the sign-in page, for a request the API refused with 401. */
  signIn(): void;
  /** The capture's moment in the main window. */
  openNotebook(id: number): void;
  /** Hands focus back to the app that was in front: app.hide(). */
  giveFocusBack(): void;
  /** Listening stopped by itself, at the time limit, while the key may still be held. */
  stoppedListening?(): void;
  now(): number;
  timers?: Timers;
  trace?(event: string, fields?: Record<string, number | string>): void;
}

export const RESULT_MS = 8000;
export const SHORTEST_MS = 400;
export const LONGEST_MS = 120_000;

type Phase = "idle" | "armed" | "listening" | "working" | "result" | "typing" | "problem";

export class Dictation {
  private phase: Phase = "idle";
  private app: string | null = null;
  private timer: unknown = null;
  private shownCapture: Capture | null = null;
  private shownVersion: Version | null = null;
  private lastAudio: CaptureRequest["audio"] | null = null;
  /** What was begun last, by number: whatever finishes for anything earlier is dropped. */
  private ticket = 0;
  /** The panel has focus: typing in it, or editing in it. */
  private focused = false;
  private readonly deps: Deps;
  private readonly timers: Timers;

  constructor(deps: Deps) {
    this.deps = deps;
    this.timers = deps.timers ?? realTimers;
  }

  get state(): Phase {
    return this.phase;
  }

  private begin(): number {
    return ++this.ticket;
  }

  private current(ticket: number): boolean {
    return ticket === this.ticket;
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

  private versions(): Version[] {
    const settings = this.deps.settings();
    return [settings.fromOwn, settings.fromEnglish];
  }

  private warm(): void {
    void this.deps.api.warm().catch(() => {});
  }

  private view(view: PanelView, focus = false): void {
    // Out of a focused panel, focus goes back to the app in front first: giving it back
    // hides every window of the app, the panel too, and the panel then comes back without
    // taking it.
    if (this.focused && !focus) this.deps.giveFocusBack();
    this.focused = focus;
    this.deps.panel.show(view, focus);
  }

  private close(): void {
    this.begin();
    this.stopTimer();
    this.phase = "idle";
    if (this.focused) this.deps.giveFocusBack();
    this.focused = false;
    this.deps.panel.hide();
  }

  private discardRecording(): void {
    if (this.phase === "armed" || this.phase === "listening") this.deps.panel.record("discard");
  }

  private work(via: Via): void {
    this.stopTimer();
    this.phase = "working";
    this.view({ kind: "working", via });
  }

  // ── The key ─────────────────────────────────────────────────────────────

  arm(app: string | null): void {
    // The next fn replaces a result or a problem still showing; it never interrupts typing,
    // an edit, listening already started, or work in flight.
    const replaceable = this.phase === "idle" || this.phase === "problem" || (this.phase === "result" && !this.focused);
    if (!replaceable) return;
    this.begin();
    this.stopTimer();
    this.phase = "armed";
    this.app = app;
    this.deps.trace?.("down", { at: this.deps.now() });
    this.deps.panel.record("start");
    this.warm();
  }

  hold(): void {
    if (this.phase === "armed") this.listen(false);
  }

  handsFree(): void {
    if (this.phase === "armed" || this.phase === "listening") this.listen(true);
  }

  private listen(handsFree: boolean): void {
    this.phase = "listening";
    this.view({ kind: "listening", handsFree, since: this.deps.now() });
    this.wait(LONGEST_MS, () => {
      this.deps.stoppedListening?.();
      this.finish();
    });
  }

  finish(): void {
    if (this.phase !== "listening") return;
    this.deps.trace?.("released", { at: this.deps.now() });
    this.deps.panel.record("stop");
    this.work("voice");
  }

  /** From the key: a shortcut, or a tap that came to nothing. Typing and work in flight are not the key's. */
  cancel(): void {
    if (this.phase === "idle" || this.phase === "typing" || this.phase === "working") return;
    this.discardRecording();
    this.close();
  }

  /** The recording, from the panel, once `record("stop")` has ended it. */
  async audio(bytes: Uint8Array, mimeType: string, durationMs: number): Promise<void> {
    if (this.phase !== "working") return;
    if (bytes.length === 0) {
      this.problem(
        "The microphone did not open",
        "Allow SpeakLab in System Settings › Privacy & Security › Microphone, then try again.",
      );
      return;
    }
    if (durationMs < SHORTEST_MS) return this.close();
    this.lastAudio = { bytes, mimeType };
    await this.send({ audio: this.lastAudio, via: "voice", app: this.app, mode: "auto", versions: this.versions(), save: this.deps.settings().save });
  }

  // ── Typing and copying ──────────────────────────────────────────────────

  typing(app: string | null): void {
    // Pressed again while typing, it leaves what is typed where it is.
    if (this.phase === "working" || this.phase === "typing") return;
    this.begin();
    this.discardRecording();
    this.stopTimer();
    this.phase = "typing";
    this.app = app;
    this.view({ kind: "typing" }, true);
    this.warm();
  }

  /** From the typing panel, for a keyboard without fn: listen until Done. */
  speakInstead(): void {
    if (this.phase !== "typing") return;
    const app = this.app;
    this.phase = "idle";
    this.arm(app);
    this.handsFree();
  }

  async text(text: string): Promise<void> {
    if (this.phase !== "typing") return;
    if (!text.trim()) return this.close();
    this.lastAudio = null;
    this.work("typed");
    await this.send({ text, via: "typed", app: this.app, mode: "auto", versions: this.versions(), save: this.deps.settings().save });
  }

  /** ⌃⌥C: what was on the clipboard, translated or checked, and put back in its place. */
  async copied(app: string | null, text: string): Promise<void> {
    if (this.phase === "working") return;
    this.discardRecording();
    if (!text.trim()) {
      this.problem("Nothing to translate", "Copy some text first, then press ⌃⌥C.");
      return;
    }
    this.app = app;
    this.lastAudio = null;
    this.work("copied");
    await this.send({ text, via: "copied", app, mode: "auto", versions: this.versions(), save: this.deps.settings().save });
  }

  // ── The result ──────────────────────────────────────────────────────────

  private async send(request: CaptureRequest): Promise<void> {
    const ticket = this.begin();
    let capture: Capture;
    try {
      capture = await this.deps.api.capture(request);
    } catch (error) {
      if (this.current(ticket)) this.failed(error);
      return;
    }
    if (!this.current(ticket)) {
      // Abandoned while it was being made: what it saved goes too.
      if (capture.id !== null) await this.deps.api.remove(capture.id).catch(() => {});
      return;
    }
    await this.show(capture, capture.chosen, ticket);
  }

  /** The version on the clipboard, and only then the panel saying so. */
  private async show(capture: Capture, version: Version, ticket: number): Promise<void> {
    this.stopTimer();
    try {
      await this.deps.writeClipboard(capture.versions[version] ?? capture.text);
    } catch (error) {
      if (this.current(ticket)) this.problem("It could not be copied", error instanceof Error ? error.message : String(error));
      return;
    }
    if (!this.current(ticket)) return;
    this.shownCapture = capture;
    this.shownVersion = version;
    this.phase = "result";
    this.deps.trace?.("copied", { at: this.deps.now(), version });
    this.view({ kind: "result", capture, shown: version, editing: false });
    this.wait(RESULT_MS, () => this.close());
  }

  private failed(error: unknown): void {
    const status = error instanceof SayApiError ? error.status : 0;
    const message = error instanceof Error ? error.message : String(error);
    if (status === 401) {
      this.deps.signIn();
      this.problem("Sign in to SpeakLab first", "Its window is open on the sign-in page. Nothing was saved.");
    } else if (status === 0) {
      this.problem("SpeakLab is not answering", "Its services may still be starting. Try again in a moment.");
    } else if (status === 422) {
      this.problem("SpeakLab could not use that", message);
    } else {
      this.problem("It could not be done", message);
    }
  }

  private problem(title: string, body: string): void {
    this.phase = "problem";
    this.view({ kind: "problem", title, body });
    this.wait(RESULT_MS, () => this.close());
  }

  /** Another version on the clipboard: the one written already, or written now. */
  async choose(version: Version): Promise<void> {
    const capture = this.shownCapture;
    if (this.phase !== "result" || !capture) return;
    const ticket = this.begin();
    if (capture.versions[version]) return this.show(capture, version, ticket);
    this.work(capture.via);
    try {
      const written =
        capture.id !== null
          ? await this.deps.api.version(capture.id, version)
          : await this.deps.api.capture({
              text: capture.source_text,
              via: capture.via,
              app: capture.app,
              mode: capture.mode,
              versions: [version],
              save: false,
            });
      if (!this.current(ticket)) return;
      await this.show(
        { ...capture, versions: { ...capture.versions, ...written.versions }, dropped: { ...capture.dropped, ...written.dropped } },
        version,
        ticket,
      );
    } catch (error) {
      if (this.current(ticket)) this.failed(error);
    }
  }

  /** The panel's switch: the other language. The wrong capture goes, and a new one is made. */
  async switchLanguage(): Promise<void> {
    const capture = this.shownCapture;
    if (this.phase !== "result" || !capture) return;
    const mode = capture.mode === "translate" ? "check" : "translate";
    this.work(capture.via);
    const ticket = this.begin();
    if (capture.id !== null) await this.deps.api.remove(capture.id).catch(() => {});
    if (!this.current(ticket)) return;
    const save = this.deps.settings().save;
    await this.send(
      this.lastAudio && capture.via === "voice"
        ? { audio: this.lastAudio, via: "voice", app: capture.app, mode, versions: this.versions(), save }
        : { text: capture.source_text, via: capture.via, app: capture.app, mode, versions: this.versions(), save },
    );
  }

  /** Edit: the panel takes focus, and stays, until the edit is copied or Esc. */
  edit(): void {
    const capture = this.shownCapture;
    if (this.phase !== "result" || !capture) return;
    this.stopTimer();
    this.view({ kind: "result", capture, shown: this.shownVersion ?? capture.chosen, editing: true }, true);
  }

  async edited(text: string): Promise<void> {
    if (this.phase !== "result") return;
    const ticket = this.begin();
    try {
      await this.deps.writeClipboard(text);
    } catch (error) {
      if (this.current(ticket)) this.problem("It could not be copied", error instanceof Error ? error.message : String(error));
      return;
    }
    if (this.current(ticket)) this.close();
  }

  /** Copy again what is shown. */
  async again(version: Version): Promise<void> {
    const capture = this.shownCapture;
    if (this.phase !== "result" || !capture) return;
    await this.show(capture, version, this.begin());
  }

  open(): void {
    if (this.phase !== "result") return;
    const id = this.shownCapture?.id ?? null;
    // Closed first: giving focus back would hide the window it opens.
    this.close();
    if (id !== null) this.deps.openNotebook(id);
  }

  /** Esc, or the panel's own close: whatever is showing goes, and work in flight is abandoned. */
  dismiss(): void {
    if (this.phase === "idle") return;
    this.discardRecording();
    this.close();
  }
}
