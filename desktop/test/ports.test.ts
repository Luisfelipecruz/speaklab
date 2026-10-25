import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, it } from "node:test";

import { describeListener, isFree, leftovers, stopLeftovers } from "../src/ports.ts";

const run = mkdtempSync(join(tmpdir(), "speaklab-ports-"));
after(() => rmSync(run, { recursive: true, force: true }));

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/** A process leading its own group, as the app starts each one. */
function group(script: string): number {
  const child = spawn("/bin/sh", ["-c", script], { detached: true, stdio: "ignore" });
  child.unref();
  return child.pid!;
}

async function gone(pid: number, withinMs = 5000): Promise<boolean> {
  const deadline = Date.now() + withinMs;
  while (alive(pid) && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20));
  return !alive(pid);
}

describe("the ports", () => {
  it("are free until something listens on them", async () => {
    const server = createServer();
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const { port } = server.address() as AddressInfo;
    assert.equal(await isFree(port), false);
    await new Promise((resolve) => server.close(resolve));
    assert.equal(await isFree(port), true);
  });

  it("name what holds them from lsof's answer", () => {
    assert.equal(describeListener("p4242\ncnode\nf23\n"), "node (pid 4242)");
    assert.equal(describeListener("p4242\n"), "a process (pid 4242)");
    assert.equal(describeListener(""), undefined);
  });
});

describe("what an earlier run left behind", () => {
  it("is what a pid file names, alive, running from the app's own resources", async () => {
    const mine = group("sleep 30");
    const other = group("sleep 30");
    writeFileSync(join(run, "asr.pid"), `${mine}\n/R/python/bin/python3.12\n`);
    writeFileSync(join(run, "tts.pid"), `${other}\n/R/python/bin/python3.12\n`);
    writeFileSync(join(run, "pron.pid"), "999999\n");
    writeFileSync(join(run, "api.pid"), "not a pid\n");
    const commands: Record<number, string> = { [mine]: "/R/python/bin/python3.12 -m uvicorn app:app", [other]: "/usr/bin/python3 server.py" };
    const found = await leftovers(run, "/R", async (pid) => commands[pid]);
    assert.deepEqual(found, [{ name: "asr", pid: mine }]);
    for (const name of ["tts", "pron", "api"]) assert.ok(!existsSync(join(run, `${name}.pid`)), `${name}.pid removed`);
    assert.ok(alive(other), "a reused pid is left alone");
    await stopLeftovers(found, 2000);
    assert.ok(await gone(mine));
    process.kill(-other, "SIGKILL");
  });

  it("is stopped with its whole group, and killed when it will not stop", async () => {
    const stubborn = group("trap '' TERM INT; sleep 30 & echo; wait");
    await new Promise((resolve) => setTimeout(resolve, 100));
    const started = Date.now();
    await stopLeftovers([{ name: "asr", pid: stubborn }], 300);
    assert.ok(await gone(stubborn));
    assert.ok(Date.now() - started >= 300, "it was given its time first");
  });

  it("is nothing when there is no run folder yet", async () => {
    assert.deepEqual(await leftovers(join(run, "absent"), "/R"), []);
  });
});
