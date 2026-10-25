// The fixed ports, checked before anything starts, and what an earlier run left behind.
// A port held by a process this app started is taken back; one held by anything else is
// named, so the person can see what is in the way.

import { execFile } from "node:child_process";
import { readdirSync, readFileSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { join } from "node:path";
import { promisify } from "node:util";

const run = promisify(execFile);

export function isFree(port: number, host = "127.0.0.1"): Promise<boolean> {
  return new Promise((resolve) => {
    const server = createServer();
    server.once("error", () => resolve(false));
    server.listen(port, host, () => server.close(() => resolve(true)));
  });
}

/** lsof's `-Fpc` output as `name (pid N)`: its first process, or undefined if it has none. */
export function describeListener(lsofOutput: string): string | undefined {
  const pid = /^p(\d+)$/m.exec(lsofOutput)?.[1];
  const command = /^c(.+)$/m.exec(lsofOutput)?.[1];
  return pid ? `${command ?? "a process"} (pid ${pid})` : undefined;
}

/** The process listening on a port, or undefined if lsof cannot tell. */
export async function owner(port: number): Promise<string | undefined> {
  try {
    const { stdout } = await run("/usr/sbin/lsof", ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN", "-Fpc"]);
    return describeListener(stdout);
  } catch {
    return undefined;
  }
}

export async function commandOf(pid: number): Promise<string | undefined> {
  try {
    const { stdout } = await run("/bin/ps", ["-o", "command=", "-p", String(pid)]);
    return stdout.trim() || undefined;
  } catch {
    return undefined;
  }
}

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export interface Leftover {
  name: string;
  pid: number;
}

/**
 * Processes an earlier run started and did not stop: a pid file whose process is alive and
 * whose command still runs from this app's own resources. A pid that was reused by
 * something else does not match and is left alone.
 */
export async function leftovers(
  runDir: string,
  resources: string,
  lookup: (pid: number) => Promise<string | undefined> = commandOf,
): Promise<Leftover[]> {
  let files: string[];
  try {
    files = readdirSync(runDir).filter((f) => f.endsWith(".pid"));
  } catch {
    return [];
  }
  const found: Leftover[] = [];
  for (const file of files) {
    const path = join(runDir, file);
    const pid = Number(readFileSync(path, "utf8").split("\n")[0]);
    const command = Number.isInteger(pid) && pid > 1 && alive(pid) ? await lookup(pid) : undefined;
    if (command?.includes(resources)) found.push({ name: file.replace(/\.pid$/, ""), pid });
    else rmSync(path, { force: true });
  }
  return found;
}

/** SIGTERM (SIGINT for Postgres) to each leftover's group, then SIGKILL after `waitMs`. */
export async function stopLeftovers(found: readonly Leftover[], waitMs = 10_000): Promise<void> {
  for (const { name, pid } of found) {
    try {
      process.kill(-pid, name === "postgres" ? "SIGINT" : "SIGTERM");
    } catch {
      // Gone already.
    }
  }
  const deadline = Date.now() + waitMs;
  while (found.some(({ pid }) => alive(pid)) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  for (const { pid } of found) {
    if (!alive(pid)) continue;
    try {
      process.kill(-pid, "SIGKILL");
    } catch {
      // Gone already.
    }
  }
}
