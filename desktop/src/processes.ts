// Real processes for the supervisor. Each is started as the leader of its own process
// group, so a stop reaches what it started too (pron's resource tracker, Postgres's
// backends), and writes to its own log in the data folder. A pid file names it while it
// runs, which is how the next launch finds what a crashed one left behind.

import { spawn } from "node:child_process";
import { closeSync, mkdirSync, openSync, readFileSync, renameSync, rmSync, statSync, writeFileSync, writeSync } from "node:fs";
import { join } from "node:path";

import type { Exit, Handle } from "./supervisor.ts";

export interface Command {
  file: string;
  args: readonly string[];
  cwd: string;
  env: Record<string, string>;
}

/** A log past this size is moved aside to `<name>.log.1` before the next start. */
const LOG_LIMIT = 10 * 1024 * 1024;

export function logPath(logs: string, name: string): string {
  return join(logs, `${name}.log`);
}

export function rotateLog(log: string): void {
  try {
    if (statSync(log).size > LOG_LIMIT) renameSync(log, `${log}.1`);
  } catch {
    // No log yet.
  }
}

/** The last `lines` lines of a log, read from its last 32 KB. */
export function tailOf(log: string, lines = 40): string {
  try {
    const text = readFileSync(log, "utf8");
    return text.slice(-32 * 1024).split("\n").slice(-lines).join("\n");
  } catch {
    return "";
  }
}

export function launch(name: string, command: Command, logs: string, run: string): Handle {
  mkdirSync(logs, { recursive: true });
  mkdirSync(run, { recursive: true });
  const log = logPath(logs, name);
  rotateLog(log);
  const fd = openSync(log, "a");
  writeSync(fd, `\n==== ${new Date().toISOString()} ${command.file} ${command.args.join(" ")}\n`);
  const child = spawn(command.file, command.args, {
    cwd: command.cwd,
    env: command.env,
    stdio: ["ignore", fd, fd],
    detached: true,
  });
  closeSync(fd);
  const pidFile = join(run, `${name}.pid`);
  if (child.pid !== undefined) writeFileSync(pidFile, `${child.pid}\n${command.file}\n`);
  const exited = new Promise<Exit>((resolve) => {
    child.once("exit", (code, signal) => {
      rmSync(pidFile, { force: true });
      resolve({ code, signal });
    });
    child.once("error", (error) => {
      writeFileSync(log, `could not start ${command.file}: ${error.message}\n`, { flag: "a" });
      rmSync(pidFile, { force: true });
      resolve({ code: 127, signal: null });
    });
  });
  return {
    pid: child.pid ?? -1,
    exited,
    kill(signal) {
      if (child.pid === undefined) return;
      try {
        process.kill(-child.pid, signal);
      } catch {
        // Already gone.
      }
    },
    tail: () => tailOf(log),
  };
}

/** Runs a command to completion and returns its exit code and output. */
export function runOnce(command: Command, timeoutMs = 10_000): Promise<{ code: number | null; output: string }> {
  return new Promise((resolve) => {
    const child = spawn(command.file, command.args, { cwd: command.cwd, env: command.env });
    let output = "";
    child.stdout.on("data", (b: Buffer) => (output += b.toString()));
    child.stderr.on("data", (b: Buffer) => (output += b.toString()));
    const timer = setTimeout(() => child.kill("SIGKILL"), timeoutMs);
    child.once("error", (error) => {
      clearTimeout(timer);
      resolve({ code: 127, output: error.message });
    });
    // close, not exit: exit can come before the output has been read to its end.
    child.once("close", (code) => {
      clearTimeout(timer);
      resolve({ code, output });
    });
  });
}
