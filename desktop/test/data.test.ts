import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, it } from "node:test";

import { clusterExists, ensureFolders, loadSecrets, writePasswordFile } from "../src/data.ts";
import { type Paths, paths } from "../src/layout.ts";

let data = "";
let p: Paths;
beforeEach(() => {
  data = mkdtempSync(join(tmpdir(), "speaklab-data-"));
  p = paths({ resources: "/R", data });
});
afterEach(() => rmSync(data, { recursive: true, force: true }));

const mode = (path: string) => statSync(path).mode & 0o777;

describe("the data folder", () => {
  it("is made with folders only this account can open", () => {
    ensureFolders(p);
    for (const dir of [join(data, "postgres"), p.audio, p.models, p.logs, p.run]) assert.equal(mode(dir), 0o700, dir);
  });

  it("is Application Support/SpeakLab: Electron names it after package.json's productName, as the bundle is", () => {
    const pkg = JSON.parse(readFileSync(join(import.meta.dirname, "..", "package.json"), "utf8")) as { productName?: string };
    assert.equal(pkg.productName, "SpeakLab");
    const builder = readFileSync(join(import.meta.dirname, "..", "build", "electron-builder.yml"), "utf8");
    assert.doesNotMatch(builder, /^productName:/m);
  });

  it("makes its two secrets once, in a file only this account can read", () => {
    const first = loadSecrets(p);
    assert.match(first.dbPassword, /^[A-Za-z0-9_-]{32}$/);
    assert.match(first.jwtSecret, /^[0-9a-f]{64}$/);
    assert.equal(mode(p.secret), 0o600);
    assert.deepEqual(loadSecrets(p), first);
    assert.notDeepEqual(loadSecrets(paths({ resources: "/R", data: join(data, "elsewhere") })), first);
  });

  it("makes new secrets when the file cannot be read as them", () => {
    writeFileSync(p.secret, "not json");
    const made = loadSecrets(p);
    assert.deepEqual(JSON.parse(readFileSync(p.secret, "utf8")), made);
  });

  it("knows a cluster by its PG_VERSION", () => {
    assert.equal(clusterExists(p), false);
    mkdirSync(p.cluster, { recursive: true });
    assert.equal(clusterExists(p), false);
    writeFileSync(join(p.cluster, "PG_VERSION"), "16\n");
    assert.equal(clusterExists(p), true);
  });

  it("writes initdb's password file 0600", () => {
    const file = writePasswordFile(p, { dbPassword: "secret-1", jwtSecret: "x" });
    assert.equal(readFileSync(file, "utf8"), "secret-1\n");
    assert.equal(mode(file), 0o600);
  });
});
