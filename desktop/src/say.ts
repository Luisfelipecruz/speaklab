// Say it in English in the running app: the panel window, the menu bar, the shortcuts, the
// fn helper and the settings window, wired to the dictation's state machine. Everything
// that decides is elsewhere (dictation.ts, keys.ts, panel.ts, tray.ts); this is the part
// that only runs inside Electron.

import { execFile } from "node:child_process";
import { appendFileSync } from "node:fs";
import { join } from "node:path";
import { promisify } from "node:util";

import {
  app,
  type BrowserWindow,
  clipboard,
  globalShortcut,
  ipcMain,
  Menu,
  nativeImage,
  net,
  screen,
  shell,
  Tray,
  type WebContents,
} from "electron";

import { Dictation, type Panel, type PanelView, type Version } from "./dictation.ts";
import { Intentions, KeyHelper } from "./keys.ts";
import { placement, PANEL_MIN_HEIGHT } from "./panel.ts";
import { sayApi } from "./say-api.ts";
import { loadSettings, parseSettings, type SaySettings, saveSettings } from "./say-settings.ts";
import { ICON_PX, ICON_SCALE, iconBitmap, trayMenu } from "./tray.ts";
import { panelWindow, settingsWindow } from "./windows.ts";

const run = promisify(execFile);

const PANES: Record<string, string> = {
  "input-monitoring": "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
  keyboard: "x-apple.systempreferences:com.apple.Keyboard-Settings.extension",
};

const LANGUAGES: Record<string, string> = {
  es: "Spanish",
  pt: "Portuguese",
  fr: "French",
  it: "Italian",
  de: "German",
  ca: "Catalan",
};

export interface SayContext {
  staticDir: string;
  userData: string;
  /** The API, and the window's origin its requests are sent from. */
  apiBase: string;
  webOrigin: string;
  /** Contents/MacOS/speaklab-keys in the bundle. */
  helper: string;
  /** The main window, on one of the web app's paths. */
  openMain(path: string): void;
  note(line: string): void;
}

/** The app in front, as macOS names it: for a shortcut, which the helper does not see. */
async function frontApp(): Promise<string | null> {
  try {
    const { stdout: asn } = await run("/usr/bin/lsappinfo", ["front"]);
    const { stdout } = await run("/usr/bin/lsappinfo", ["info", "-only", "name", asn.trim()]);
    return /"LSDisplayName"="([^"]*)"/.exec(stdout)?.[1] ?? null;
  } catch {
    return null;
  }
}

/** What *Press 🌐 key to* is set to: 0 is Do Nothing, null is never set. */
async function globeSetting(): Promise<number | null> {
  try {
    const { stdout } = await run("/usr/bin/defaults", ["read", "com.apple.HIToolbox", "AppleFnUsageType"]);
    const value = Number(stdout.trim());
    return Number.isInteger(value) ? value : null;
  } catch {
    return null;
  }
}

export class SayFeature {
  settings: SaySettings;
  private readonly ctx: SayContext;
  private readonly file: string;
  private panel: BrowserWindow | null = null;
  private tray: Tray | null = null;
  private helper: KeyHelper | null = null;
  private settingsWin: BrowserWindow | null = null;
  private access: boolean | null = null;
  private language = "your language";
  private escape = false;
  private readonly dictation: Dictation;
  private readonly intentions: Intentions;

  constructor(ctx: SayContext) {
    this.ctx = ctx;
    this.file = join(ctx.userData, "say.json");
    this.settings = loadSettings(this.file);
    const trace = process.env.SPEAKLAB_SAY_TRACE;
    this.dictation = new Dictation({
      api: sayApi(ctx.apiBase, ctx.webOrigin),
      panel: this.panelPort(),
      writeClipboard: (text) => clipboard.writeText(text),
      settings: () => this.settings,
      signIn: () => ctx.openMain("/login?next=/notebook"),
      openNotebook: (id) => ctx.openMain(`/notebook/${id}`),
      giveFocusBack: () => app.hide(),
      stoppedListening: () => this.intentions.forget(),
      now: () => Date.now(),
      // Times and states only, never words: for the measurement harness.
      ...(trace ? { trace: (event: string, fields = {}) => appendFileSync(trace, `${JSON.stringify({ event, ...fields })}\n`) } : {}),
    });
    this.intentions = new Intentions({
      arm: (frontmost) => this.dictation.arm(frontmost),
      hold: () => this.dictation.hold(),
      handsFree: () => this.dictation.handsFree(),
      finish: () => this.dictation.finish(),
      cancel: () => this.dictation.cancel(),
    });
    this.wire();
  }

  isPanel(contents: WebContents | null): boolean {
    return Boolean(contents && this.panel && contents === this.panel.webContents);
  }

  start(): void {
    if (!this.settings.enabled) return;
    if (!this.panel) {
      this.panel = panelWindow(join(this.ctx.staticDir, "panel.html"), join(this.ctx.staticDir, "panel-preload.cjs"));
    }
    if (!this.tray) {
      const image = nativeImage.createFromBitmap(iconBitmap(), { width: ICON_PX, height: ICON_PX, scaleFactor: ICON_SCALE });
      image.setTemplateImage(true);
      this.tray = new Tray(image);
      this.tray.setToolTip("Say it in English");
    }
    this.menu();
    globalShortcut.register("Control+Alt+Space", () => void frontApp().then((front) => this.dictation.typing(front)));
    globalShortcut.register("Control+Alt+C", () => this.copied());
    if (this.settings.key === "fn") this.startHelper();
    app.setLoginItemSettings({ openAtLogin: this.settings.openAtLogin });
    this.ctx.note("say on");
  }

  stop(): void {
    this.helper?.stop();
    this.helper = null;
    globalShortcut.unregister("Control+Alt+Space");
    globalShortcut.unregister("Control+Alt+C");
    this.unregisterEscape();
    this.tray?.destroy();
    this.tray = null;
    this.panel?.destroy();
    this.panel = null;
  }

  /** The account's language by name, for the menu, once the API answers. */
  learnLanguage(): void {
    const request = net.request({ url: `${this.ctx.apiBase}/auth/me`, origin: this.ctx.webOrigin, useSessionCookies: true });
    request.on("response", (response) => {
      const chunks: Buffer[] = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        try {
          const code = (JSON.parse(Buffer.concat(chunks).toString("utf8")) as { native_language?: string }).native_language;
          if (code && LANGUAGES[code]) {
            this.language = LANGUAGES[code];
            this.menu();
          }
        } catch {
          // Not signed in yet: the menu says "your language".
        }
      });
    });
    request.on("error", () => {});
    request.end();
  }

  /** ⌃⌥C, from the shortcut or the menu: the app in front, and what is on the clipboard. */
  private copied(): void {
    void Promise.all([frontApp(), clipboard.readText().catch(() => "")]).then(([front, text]) =>
      this.dictation.copied(front, text),
    );
  }

  private startHelper(): void {
    // For the measurement harness: the key's lines read from a pipe it writes, in place
    // of the helper's from the keyboard.
    const played = process.env.SPEAKLAB_SAY_KEYS;
    this.helper = new KeyHelper({
      file: played ? "/bin/cat" : this.ctx.helper,
      ...(played ? { args: [played] } : {}),
      onEvent: (event) => {
        if (event.t === "access") {
          this.access = event.granted;
          this.ctx.note(`input monitoring ${event.granted ? "granted" : "not granted"}`);
          this.menu();
          this.sendSettings();
        } else {
          this.intentions.key(event);
        }
      },
      onExit: (code) => this.ctx.note(`speaklab-keys exited ${code}`),
    });
    this.helper.start();
  }

  private menu(): void {
    if (!this.tray) return;
    const template = trayMenu(
      { settings: this.settings, access: this.access, language: this.language },
      {
        type: () => void frontApp().then((front) => this.dictation.typing(front)),
        copied: () => this.copied(),
        fromOwn: (version) => this.apply({ ...this.settings, fromOwn: version }),
        save: (on) => this.apply({ ...this.settings, save: on }),
        notebook: () => this.ctx.openMain("/notebook"),
        settings: () => this.openSettings(),
        quit: () => app.quit(),
      },
    );
    this.tray.setContextMenu(Menu.buildFromTemplate(template));
  }

  apply(next: SaySettings): void {
    const before = this.settings;
    this.settings = parseSettings(next);
    saveSettings(this.file, this.settings);
    if (before.enabled !== this.settings.enabled) {
      if (this.settings.enabled) this.start();
      else this.stop();
    } else if (this.settings.enabled && before.key !== this.settings.key) {
      if (this.settings.key === "fn") this.startHelper();
      else {
        this.helper?.stop();
        this.helper = null;
      }
    }
    if (before.openAtLogin !== this.settings.openAtLogin) {
      app.setLoginItemSettings({ openAtLogin: this.settings.openAtLogin });
    }
    this.menu();
    this.sendSettings();
  }

  openSettings(): void {
    if (this.settingsWin && !this.settingsWin.isDestroyed()) {
      this.settingsWin.focus();
      return;
    }
    this.settingsWin = settingsWindow(join(this.ctx.staticDir, "settings.html"), join(this.ctx.staticDir, "settings-preload.cjs"));
    this.settingsWin.webContents.once("did-finish-load", () => this.sendSettings());
    this.settingsWin.on("closed", () => (this.settingsWin = null));
  }

  private sendSettings(): void {
    if (!this.settingsWin || this.settingsWin.isDestroyed()) return;
    void globeSetting().then((globe) =>
      this.settingsWin?.webContents.send("settings:state", { settings: this.settings, access: this.access, globe }),
    );
  }

  private registerEscape(): void {
    if (this.escape) return;
    this.escape = globalShortcut.register("Escape", () => {
      this.intentions.escape();
      this.dictation.dismiss();
    });
  }

  private unregisterEscape(): void {
    if (!this.escape) return;
    globalShortcut.unregister("Escape");
    this.escape = false;
  }

  private place(height: number): void {
    const panel = this.panel;
    if (!panel) return;
    const display = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
    panel.setBounds(placement(display.workArea, height));
  }

  private panelPort(): Panel {
    return {
      show: (view: PanelView, focus: boolean) => {
        const panel = this.panel;
        if (!panel) return;
        panel.webContents.send("panel:state", view);
        if (!panel.isVisible()) this.place(PANEL_MIN_HEIGHT);
        if (focus) {
          panel.setFocusable(true);
          panel.show();
          panel.focus();
        } else {
          panel.setFocusable(false);
          panel.showInactive();
        }
        this.registerEscape();
      },
      hide: () => {
        this.panel?.hide();
        this.panel?.setFocusable(false);
        this.unregisterEscape();
      },
      record: (command) => this.panel?.webContents.send("panel:record", command),
    };
  }

  private wire(): void {
    ipcMain.on("panel:audio", (_event, bytes: Uint8Array, mimeType: string, durationMs: number) => {
      void this.dictation.audio(bytes, mimeType, durationMs);
    });
    ipcMain.on("panel:text", (_event, text: string) => void this.dictation.text(text));
    ipcMain.on("panel:choose", (_event, choice: { version: Version; again: boolean }) => {
      if (choice.again) void this.dictation.again(choice.version);
      else void this.dictation.choose(choice.version);
    });
    ipcMain.on("panel:edited", (_event, text: string) => void this.dictation.edited(text));
    ipcMain.on("panel:act", (_event, action: string) => {
      switch (action) {
        case "dismiss":
          this.intentions.escape();
          this.dictation.dismiss();
          return;
        case "open":
          return this.dictation.open();
        case "edit":
          return this.dictation.edit();
        case "done":
          // The key's hands-free ends with it; the dictation's own finish covers listening
          // the key never saw.
          this.intentions.done();
          this.dictation.finish();
          return;
        case "switch":
          return void this.dictation.switchLanguage();
        case "speak":
          this.dictation.speakInstead();
          if (this.dictation.state === "listening") this.intentions.listenWithoutKey();
          return;
      }
    });
    ipcMain.on("panel:size", (_event, height: number) => this.place(height));
    ipcMain.on("settings:save", (_event, next: unknown) => this.apply(parseSettings(next)));
    ipcMain.on("settings:open", (_event, pane: string) => {
      const url = PANES[pane];
      if (url) void shell.openExternal(url);
    });
  }
}
