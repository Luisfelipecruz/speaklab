// The windows and what their pages may do. Electron grants every permission unless told
// otherwise: here audio capture is the one thing allowed, for the app's own origin and for
// the Say it in English panel, and macOS is asked for the microphone the first time a
// recording starts, not at launch. Links that leave the app open in the browser instead
// of in the window.

import { app, BrowserWindow, type Session, shell, systemPreferences, type WebContents } from "electron";

import { PANEL_SPACES, panelOptions } from "./panel.ts";

export function originOf(url: string): string {
  try {
    return new URL(url).origin;
  } catch {
    return "";
  }
}

export function installPermissions(
  ses: Session,
  origin: string,
  isPanel: (contents: WebContents | null) => boolean = () => false,
): void {
  // The check handler is given the origin with a trailing slash ("http://127.0.0.1:3013/")
  // and the request handler a full URL, so both are normalised before comparing. The
  // panel's page is a local file, whose origin is opaque, so it is known by its contents.
  ses.setPermissionRequestHandler((contents, permission, callback, details) => {
    const types = "mediaTypes" in details ? (details.mediaTypes ?? []) : [];
    const audioOnly = types.length > 0 && types.every((t) => t === "audio");
    const ours = originOf(details.requestingUrl) === origin || isPanel(contents);
    if (permission === "media" && audioOnly && ours) {
      // Chromium's fake capture device (the smoke test's) reads no microphone, so macOS
      // is not asked about one.
      if (app.commandLine.hasSwitch("use-fake-device-for-media-stream")) return callback(true);
      systemPreferences.askForMediaAccess("microphone").then(callback, () => callback(false));
      return;
    }
    callback(false);
  });
  ses.setPermissionCheckHandler(
    (contents, permission, requestingOrigin, details) =>
      permission === "media" &&
      (originOf(requestingOrigin) === origin || isPanel(contents)) &&
      details.mediaType !== "video",
  );
}

function keepInside(win: BrowserWindow, origin: string): void {
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) void shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (originOf(url) === origin || url.startsWith("file:")) return;
    event.preventDefault();
    if (url.startsWith("https://")) void shell.openExternal(url);
  });
}

export function statusWindow(html: string, preload: string): BrowserWindow {
  const win = new BrowserWindow({
    width: 560,
    height: 460,
    resizable: false,
    title: "SpeakLab",
    show: false,
    webPreferences: { preload, contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  keepInside(win, "file://");
  win.once("ready-to-show", () => win.show());
  void win.loadFile(html);
  return win;
}

export function mainWindow(url: string): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 760,
    minHeight: 560,
    title: "SpeakLab",
    show: false,
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  keepInside(win, originOf(url));
  win.once("ready-to-show", () => win.show());
  void win.loadURL(url);
  return win;
}

/** The Say it in English panel, made hidden at launch: panel.ts says how and why. */
export function panelWindow(html: string, preload: string): BrowserWindow {
  const win = new BrowserWindow(panelOptions(preload));
  win.setAlwaysOnTop(true, "screen-saver");
  win.setVisibleOnAllWorkspaces(true, PANEL_SPACES);
  keepInside(win, "file://");
  void win.loadFile(html);
  return win;
}

export function settingsWindow(html: string, preload: string): BrowserWindow {
  const win = new BrowserWindow({
    width: 600,
    height: 720,
    minWidth: 520,
    title: "SpeakLab Settings",
    show: false,
    webPreferences: { preload, contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  keepInside(win, "file://");
  win.once("ready-to-show", () => win.show());
  void win.loadFile(html);
  return win;
}
