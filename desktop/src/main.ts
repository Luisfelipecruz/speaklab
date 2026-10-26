// SpeakLab for this Mac. A status window while the system comes up; the services as
// processes under the supervisor; the standalone Next server in a utility process; one
// window on it; and, while Say it in English is on, the fn key, its panel and the menu bar,
// which keep the app running when the window closes. Quitting stops everything, Postgres
// last.

import { execFileSync } from "node:child_process";
import { appendFileSync, createWriteStream, readFileSync } from "node:fs";
import { cpus, homedir, tmpdir } from "node:os";
import { dirname, join } from "node:path";

import { app, BrowserWindow, dialog, ipcMain, Menu, session, shell, utilityProcess, type UtilityProcess } from "electron";

import { backup } from "./backup.ts";
import { clusterExists, ensureFolders, loadSecrets } from "./data.ts";
import { baseEnv, HOST, PORTS, type Secrets, type Settings } from "./environment.ts";
import { type Layout, paths } from "./layout.ts";
import { isFree, leftovers, owner, stopLeftovers } from "./ports.ts";
import { rotateLog } from "./processes.ts";
import { describeFailures, labelOf, llmNotice as noticeOf } from "./notices.ts";
import { quitsWhenWindowsClose } from "./panel.ts";
import { SayFeature } from "./say.ts";
import { buildSpecs } from "./specs.ts";
import { type Change, Supervisor } from "./supervisor.ts";
import { fetchMissing, type Manifest, missing, type Progress, totalBytes } from "./weights.ts";
import { installPermissions, mainWindow, statusWindow } from "./windows.ts";

const here = import.meta.dirname;
const staticDir = join(here, "..", "static");
if (process.env.SPEAKLAB_DATA) app.setPath("userData", process.env.SPEAKLAB_DATA);
const layout: Layout = {
  resources: app.isPackaged ? process.resourcesPath : join(here, "..", ".build", "stage"),
  data: app.getPath("userData"),
};
const p = paths(layout);
const base = baseEnv(homedir(), tmpdir());
const origin = `http://${HOST}:${PORTS.web}`;

interface Problem {
  title: string;
  body: string;
}

interface View {
  phase: "starting" | "downloading" | "problem" | "running";
  units: Record<string, { label: string; state: string; detail?: string }>;
  download?: Progress;
  problem?: Problem;
  notice?: string;
}

let view: View = { phase: "starting", units: {} };
let status: BrowserWindow | undefined;
let main: BrowserWindow | undefined;
let supervisor: Supervisor | undefined;
let web: UtilityProcess | undefined;
let secrets: Secrets | undefined;
let say: SayFeature | undefined;
/** The window's server answers: until then there is nothing to open a window on. */
let webReady = false;
let quitting = false;
let stopped = false;
let retrying = false;

/** CTranslate2's threads: the performance cores, at most 8, which matched Docker here. */
function settings(): Settings {
  const fromEnv = Number(process.env.SPEAKLAB_WHISPER_THREADS);
  if (Number.isInteger(fromEnv) && fromEnv > 0) return { whisperThreads: fromEnv };
  let performance = Math.max(1, Math.floor(cpus().length / 2));
  try {
    performance = Number(execFileSync("/usr/sbin/sysctl", ["-n", "hw.perflevel0.physicalcpu"]).toString().trim()) || performance;
  } catch {
    // Not an Apple silicon Mac.
  }
  return { whisperThreads: Math.min(8, performance) };
}

function publish(change: Partial<View>): void {
  view = { ...view, ...change };
  if (!status || status.isDestroyed()) {
    if (view.phase === "running" && !view.notice) return;
    status = statusWindow(join(staticDir, "status.html"), join(staticDir, "status-preload.cjs"));
    status.webContents.once("did-finish-load", () => status?.webContents.send("status", view));
  }
  status.webContents.send("status", view);
}

/** One line in logs/supervisor.log: what started, stopped and failed, and when. */
function note(line: string): void {
  try {
    appendFileSync(join(p.logs, "supervisor.log"), `${new Date().toISOString()} ${line}\n`);
  } catch {
    // The folder is made before anything is noted; a full disk is reported elsewhere.
  }
}

function onUnit(change: Change): void {
  note(`${change.name} ${change.state}${change.detail ? `: ${change.detail}` : ""}`);
  const unit = { label: labelOf(change.name), state: change.state, ...(change.detail ? { detail: change.detail } : {}) };
  publish({ units: { ...view.units, [change.name]: unit } });
  if (view.phase === "running" && change.state === "failed") {
    problem("Part of SpeakLab stopped", `${describeFailures(view.units)}\n\nTry again starts everything again.`);
  }
}

function problem(title: string, body: string): void {
  publish({ phase: "problem", problem: { title, body } });
}

async function waitForHttp(url: string, limitMs: number): Promise<boolean> {
  const deadline = Date.now() + limitMs;
  while (Date.now() < deadline) {
    try {
      await fetch(url, { signal: AbortSignal.timeout(2000) });
      return true;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
  }
  return false;
}

function startWeb(): void {
  const log = createWriteStream(join(p.logs, "web.log"), { flags: "a" });
  const server = utilityProcess.fork(join(p.web, "server.js"), [], {
    cwd: p.web,
    serviceName: "SpeakLab web",
    stdio: "pipe",
    env: {
      ...base,
      PORT: String(PORTS.web),
      HOSTNAME: HOST,
      INTERNAL_API_URL: `http://${HOST}:${PORTS.api}`,
      NODE_ENV: "production",
      NEXT_TELEMETRY_DISABLED: "1",
    },
  });
  web = server;
  server.stdout?.pipe(log);
  server.stderr?.pipe(log);
  server.once("exit", (code) => {
    // A server stopped on purpose has been replaced, or cleared, by then.
    if (web !== server) return;
    web = undefined;
    if (!quitting) problem("The window's server stopped", `It exited with code ${code}. Try again starts everything again, and Show logs opens web.log, which says why.`);
  });
}

/** What the API says about the language model, in words, or undefined when it is fine. */
async function llmNotice(): Promise<string | undefined> {
  try {
    const response = await fetch(`http://${HOST}:${PORTS.api}/health/models`, { signal: AbortSignal.timeout(5000) });
    const body = (await response.json()) as { services?: { llm?: { status?: string; detail?: string } } };
    return noticeOf(body.services?.llm);
  } catch {
    return "The language model could not be checked.";
  }
}

async function bringUp(): Promise<void> {
  publish({ phase: "starting", units: {}, problem: undefined, notice: undefined, download: undefined });
  ensureFolders(p);
  rotateLog(join(p.logs, "supervisor.log"));
  note(`launch ${app.getVersion()} from ${layout.resources}`);
  secrets = loadSecrets(p);
  const found = await leftovers(p.run, layout.resources);
  if (found.length > 0) {
    note(`stopping what an earlier run left: ${found.map((f) => `${f.name} (pid ${f.pid})`).join(", ")}`);
    await stopLeftovers(found);
  }
  for (const port of Object.values(PORTS)) {
    if (!(await isFree(port))) {
      const who = await owner(port);
      return problem(`Port ${port} is in use`, `${who ?? "Another process"} is listening on ${port}, which SpeakLab needs. Quit it, then try again.`);
    }
  }
  const manifest = JSON.parse(readFileSync(join(staticDir, "weights.json"), "utf8")) as Manifest;
  if (missing(p.models, manifest).length > 0) {
    publish({ phase: "downloading", download: { done: 0, total: totalBytes(manifest), file: "" } });
    try {
      await fetchMissing(p.models, manifest, (progress) => publish({ download: progress }));
    } catch (error) {
      return problem("The speech models could not be downloaded", `${(error as Error).message}. Check the connection, then try again; what was already downloaded is kept.`);
    }
    publish({ phase: "starting", download: undefined });
  }
  if (quitting) return;
  const firstLaunch = !clusterExists(p);
  const current = new Supervisor(buildSpecs({ p, base, secrets, settings: settings(), firstLaunch }), onUnit);
  supervisor = current;
  const started = current.start();
  // The window needs the API and nothing else, as Compose's frontend does: the model
  // services go on loading behind it, and one that fails is reported when it does.
  if (!(await current.settled("api"))) {
    if (quitting || supervisor !== current) return;
    return problem("SpeakLab could not start", describeFailures(view.units));
  }
  void started.then((failed) => {
    if (supervisor !== current) return;
    if (failed.length > 0 && view.phase === "running") problem("Part of SpeakLab stopped", `${describeFailures(view.units)}\n\nTry again starts everything again.`);
  });
  startWeb();
  if (!(await waitForHttp(origin, 60_000))) return problem("The window's server did not answer", "Show logs opens web.log, which says why.");
  note("web ready");
  webReady = true;
  // A cluster made by this launch has no account in it yet.
  openMain(firstLaunch ? "/register" : "/");
  main?.once("ready-to-show", () => note("window shown"));
  say?.learnLanguage();
  const notice = await llmNotice();
  publish({ phase: "running", notice });
  if (!notice) status?.close();
}

/** The window, on one of the web app's paths: the one open, or a new one. */
function openMain(path: string): void {
  if (!webReady) {
    status?.focus();
    return;
  }
  const url = `${origin}${path}`;
  if (main && !main.isDestroyed()) {
    void main.loadURL(url);
    main.show();
    main.focus();
  } else {
    main = mainWindow(url);
    main.on("closed", () => (main = undefined));
  }
  app.focus({ steal: true });
}

async function shutdown(): Promise<void> {
  note("stopping");
  webReady = false;
  web?.kill();
  web = undefined;
  await supervisor?.stop();
  supervisor = undefined;
}

async function retry(): Promise<void> {
  // A second press while the first is still starting everything again does nothing.
  if (retrying) return;
  retrying = true;
  try {
    if (view.phase === "running" && view.notice) {
      const notice = await llmNotice();
      publish({ notice });
      if (!notice) status?.close();
      return;
    }
    main?.close();
    await shutdown();
    await bringUp().catch((error: Error) => problem("SpeakLab could not start", error.message));
  } finally {
    retrying = false;
  }
}

async function backUp(): Promise<void> {
  if (!secrets) return;
  const choice = await dialog.showOpenDialog({
    title: "Back up SpeakLab",
    message: "Choose where to put the backup folder.",
    properties: ["openDirectory", "createDirectory"],
  });
  const into = choice.filePaths[0];
  if (choice.canceled || !into) return;
  try {
    const folder = await backup(p, base, secrets, into, app.getVersion());
    void dialog.showMessageBox({ message: "Backed up", detail: folder });
  } catch (error) {
    void dialog.showMessageBox({ type: "error", message: "The backup failed", detail: (error as Error).message });
  }
}

function menu(): void {
  Menu.setApplicationMenu(
    Menu.buildFromTemplate([
      { role: "appMenu" },
      {
        label: "File",
        submenu: [
          { label: "Back Up…", click: () => void backUp() },
          { label: "Show Logs", click: () => void shell.openPath(p.logs) },
          { type: "separator" },
          // Here as well as in the menu bar, which is gone while the feature is off.
          { label: "Say it in English Settings…", click: () => say?.openSettings() },
          { type: "separator" },
          { role: "close" },
        ],
      },
      { role: "editMenu" },
      {
        label: "View",
        submenu: [
          { role: "reload" },
          ...(app.isPackaged ? [] : [{ role: "toggleDevTools" as const }]),
          { type: "separator" },
          { role: "resetZoom" },
          { role: "zoomIn" },
          { role: "zoomOut" },
        ],
      },
      { role: "windowMenu" },
    ]),
  );
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => (main ?? status)?.focus());
  ipcMain.on("status-action", (_event, action: string) => {
    if (action === "retry") void retry();
    else if (action === "logs") void shell.openPath(p.logs);
    else if (action === "quit") app.quit();
    else if (action === "close") status?.close();
  });
  app.whenReady().then(() => {
    say = new SayFeature({
      staticDir,
      userData: layout.data,
      apiBase: `http://${HOST}:${PORTS.api}`,
      webOrigin: origin,
      helper: app.isPackaged
        ? join(dirname(process.execPath), "speaklab-keys")
        : join(here, "..", ".build", "native", "speaklab-keys"),
      openMain,
      note,
    });
    installPermissions(session.defaultSession, origin, (contents) => say?.isPanel(contents) ?? false);
    menu();
    say.start();
    void bringUp().catch((error: Error) => problem("SpeakLab could not start", error.message));
  });
  // While Say it in English is on its panel and the menu bar keep the app running; the
  // Dock icon brings the window back.
  app.on("window-all-closed", () => {
    if (!say || quitsWhenWindowsClose(say.settings)) app.quit();
  });
  app.on("activate", () => {
    if (!main && view.phase === "running") openMain("/");
  });
  app.on("before-quit", (event) => {
    if (stopped) return;
    event.preventDefault();
    if (quitting) return;
    quitting = true;
    say?.stop();
    void shutdown().finally(() => {
      stopped = true;
      app.quit();
    });
  });
  for (const signal of ["SIGTERM", "SIGINT"] as const) process.on(signal, () => app.quit());
}
