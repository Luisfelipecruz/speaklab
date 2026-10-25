// The two windows and what the page may do. Electron grants every permission unless told
// otherwise: here audio capture for the app's own origin is the one thing allowed, and
// macOS is asked for the microphone the first time a recording starts, not at launch.
// Links that leave the app open in the browser instead of in the window.

import { app, BrowserWindow, type Session, shell, systemPreferences } from "electron";

export function originOf(url: string): string {
  try {
    return new URL(url).origin;
  } catch {
    return "";
  }
}

export function installPermissions(ses: Session, origin: string): void {
  // The check handler is given the origin with a trailing slash ("http://127.0.0.1:3013/")
  // and the request handler a full URL, so both are normalised before comparing.
  ses.setPermissionRequestHandler((_contents, permission, callback, details) => {
    const types = "mediaTypes" in details ? (details.mediaTypes ?? []) : [];
    const audioOnly = types.length > 0 && types.every((t) => t === "audio");
    if (permission === "media" && audioOnly && originOf(details.requestingUrl) === origin) {
      // Chromium's fake capture device (the smoke test's) reads no microphone, so macOS
      // is not asked about one.
      if (app.commandLine.hasSwitch("use-fake-device-for-media-stream")) return callback(true);
      systemPreferences.askForMediaAccess("microphone").then(callback, () => callback(false));
      return;
    }
    callback(false);
  });
  ses.setPermissionCheckHandler(
    (_contents, permission, requestingOrigin, details) =>
      permission === "media" && originOf(requestingOrigin) === origin && details.mediaType !== "video",
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
