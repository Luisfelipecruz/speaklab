import assert from "node:assert/strict";
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, beforeEach, describe, it } from "node:test";

import { backup, stampOf } from "../src/backup.ts";
import { baseEnv } from "../src/environment.ts";
import { type Paths, paths } from "../src/layout.ts";

const root = mkdtempSync(join(tmpdir(), "speaklab-backup-"));
after(() => rmSync(root, { recursive: true, force: true }));
const secrets = { dbPassword: "pw-backup", jwtSecret: "x" };
const now = new Date(2026, 9, 25, 14, 30);

let p: Paths;
let resources = "";
let into = "";

/** Stand-ins for the bundle's psql and pg_dump: each writes what it was given. */
function tools(resources: string, dumpExit = 0): void {
  const bin = join(resources, "pg", "bin");
  mkdirSync(bin, { recursive: true });
  writeFileSync(join(bin, "psql"), "#!/bin/sh\necho 0008\n");
  writeFileSync(
    join(bin, "pg_dump"),
    `#!/bin/sh
if [ ${dumpExit} -ne 0 ]; then echo "connection refused" >&2; exit ${dumpExit}; fi
while [ $# -gt 0 ]; do [ "$1" = -f ] && out=$2; shift; done
printf 'args ok\\npassword %s\\n' "$PGPASSWORD" > "$out"
`,
  );
  chmodSync(join(bin, "psql"), 0o755);
  chmodSync(join(bin, "pg_dump"), 0o755);
}

beforeEach(() => {
  const run = mkdtempSync(join(root, "run-"));
  resources = join(run, "R");
  p = paths({ resources, data: join(run, "data") });
  into = join(run, "chosen");
  mkdirSync(into);
  mkdirSync(join(p.audio, "7"), { recursive: true });
  writeFileSync(join(p.audio, "7", "abc123"), "recording bytes");
});

describe("a backup", () => {
  it("is a folder named for the minute, with the dump, the recordings and what they are", async () => {
    tools(resources);
    const folder = await backup(p, baseEnv("/Users/someone", "/tmp"), secrets, into, "0.25.0", now);
    assert.equal(folder, join(into, "SpeakLab backup 2026-10-25 14-30"));
    assert.equal(readFileSync(join(folder, "speaklab.dump"), "utf8"), "args ok\npassword pw-backup\n");
    assert.equal(readFileSync(join(folder, "audio", "7", "abc123"), "utf8"), "recording bytes");
    const about = JSON.parse(readFileSync(join(folder, "backup.json"), "utf8")) as Record<string, string>;
    assert.equal(about.version, "0.25.0");
    assert.equal(about.schema, "0008");
  });

  it("fails with pg_dump's own words, and does not pretend", async () => {
    tools(resources, 1);
    await assert.rejects(backup(p, baseEnv("/Users/someone", "/tmp"), secrets, into, "0.25.0", now), /pg_dump failed: connection refused/);
  });

  it("never writes over an earlier one from the same minute", async () => {
    tools(resources);
    await backup(p, baseEnv("/Users/someone", "/tmp"), secrets, into, "0.25.0", now);
    await assert.rejects(backup(p, baseEnv("/Users/someone", "/tmp"), secrets, into, "0.25.0", now), /EEXIST/);
  });

  it("is stamped in the Mac's own time", () => {
    assert.equal(stampOf(new Date(2026, 0, 2, 3, 4)), "2026-01-02 03-04");
  });
});
