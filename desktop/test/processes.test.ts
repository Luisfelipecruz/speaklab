import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, it } from "node:test";

import { launch, logPath, runOnce, tailOf } from "../src/processes.ts";

const root = mkdtempSync(join(tmpdir(), "speaklab-processes-"));
after(() => rmSync(root, { recursive: true, force: true }));
const logs = join(root, "logs");
const run = join(root, "run");
const sh = (script: string) => ({ file: "/bin/sh", args: ["-c", script], cwd: root, env: { PATH: "/usr/bin:/bin" } });

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

describe("a launched process", () => {
  it("writes to its own log, is named by a pid file while it runs, and reports its exit", async () => {
    const handle = launch("job", sh("echo to-out; echo to-err >&2; sleep 0.2; exit 3"), logs, run);
    assert.equal(readFileSync(join(run, "job.pid"), "utf8").split("\n")[0], String(handle.pid));
    assert.deepEqual(await handle.exited, { code: 3, signal: null });
    assert.ok(!existsSync(join(run, "job.pid")));
    const log = readFileSync(logPath(logs, "job"), "utf8");
    assert.match(log, /==== .* \/bin\/sh -c echo to-out/);
    assert.match(log, /to-out\nto-err\n/);
    assert.match(handle.tail(), /to-err/);
  });

  it("gets only the environment it is given", async () => {
    process.env.SPEAKLAB_LEAK = "1";
    try {
      const handle = launch("env", sh('echo "leak=${SPEAKLAB_LEAK:-none}"'), logs, run);
      await handle.exited;
      assert.match(readFileSync(logPath(logs, "env"), "utf8"), /leak=none/);
    } finally {
      delete process.env.SPEAKLAB_LEAK;
    }
  });

  it("is stopped with everything it started", async () => {
    const handle = launch("tree", sh(`sleep 30 & echo $! > ${join(root, "child.pid")}; wait`), logs, run);
    const childFile = join(root, "child.pid");
    while (!existsSync(childFile) || readFileSync(childFile, "utf8").trim() === "") await new Promise((r) => setTimeout(r, 10));
    const child = Number(readFileSync(childFile, "utf8"));
    handle.kill("SIGTERM");
    assert.equal((await handle.exited).signal, "SIGTERM");
    const deadline = Date.now() + 2000;
    while (alive(child) && Date.now() < deadline) await new Promise((r) => setTimeout(r, 20));
    assert.ok(!alive(child), "the child went with its parent");
  });

  it("reports a command that cannot start as exit 127, in its log", async () => {
    const handle = launch("missing", { file: join(root, "absent"), args: [], cwd: root, env: {} }, logs, run);
    assert.deepEqual(await handle.exited, { code: 127, signal: null });
    assert.match(readFileSync(logPath(logs, "missing"), "utf8"), /could not start/);
  });

  it("moves a log past 10 MB aside before it starts again", async () => {
    writeFileSync(logPath(logs, "big"), Buffer.alloc(11 * 1024 * 1024, 65));
    await launch("big", sh("echo fresh"), logs, run).exited;
    assert.equal(statSync(`${logPath(logs, "big")}.1`).size, 11 * 1024 * 1024);
    assert.ok(statSync(logPath(logs, "big")).size < 1024);
  });
});

describe("a command run once", () => {
  it("returns its exit code and its output", async () => {
    assert.deepEqual(await runOnce(sh("echo hi; exit 2")), { code: 2, output: "hi\n" });
  });

  it("is killed when it runs past its time", async () => {
    const started = Date.now();
    const result = await runOnce(sh("exec sleep 5"), 200);
    assert.equal(result.code, null);
    assert.ok(Date.now() - started < 3000);
  });
});

describe("a log's tail", () => {
  it("is its last lines, and empty when there is no log", () => {
    writeFileSync(join(root, "t.log"), Array.from({ length: 100 }, (_, i) => `line ${i}`).join("\n"));
    assert.equal(tailOf(join(root, "t.log"), 2), "line 98\nline 99");
    assert.equal(tailOf(join(root, "absent.log")), "");
  });
});
