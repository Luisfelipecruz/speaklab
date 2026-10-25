import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { after, before, beforeEach, describe, it } from "node:test";

import { fetchMissing, type Manifest, missing, type Progress, targetOf, totalBytes } from "../src/weights.ts";

const big = randomBytes(300_000);
const small = Buffer.from('{"model_type": "test"}\n');
const sha = (b: Buffer) => createHash("sha256").update(b).digest("hex");
const REVISION = "0123456789abcdef0123456789abcdef01234567";
const manifest: Manifest = {
  models: [
    {
      repo: "org/model",
      revision: REVISION,
      files: [
        { path: "config.json", size: small.length, sha256: sha(small) },
        { path: "model.bin", size: big.length, sha256: sha(big) },
      ],
    },
  ],
};

/** A stand-in for the Hub's resolve URLs, with Range, counting what it is asked. */
let server: Server;
let baseUrl = "";
let served: Record<string, Buffer> = {};
let requests: { path: string; range?: string }[] = [];
let honourRange = true;

before(async () => {
  server = createServer((request, response) => {
    const path = request.url ?? "";
    const range = request.headers.range;
    requests.push(range ? { path, range } : { path });
    const body = served[path];
    if (!body) {
      response.writeHead(404).end();
      return;
    }
    const from = honourRange && range ? Number(/^bytes=(\d+)-$/.exec(range)?.[1]) : 0;
    response.writeHead(from > 0 ? 206 : 200, { "content-length": body.length - from });
    response.end(body.subarray(from));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
after(() => server.close());

let models = "";
beforeEach(() => {
  models = mkdtempSync(join(tmpdir(), "speaklab-weights-"));
  served = {
    [`/org/model/resolve/${REVISION}/config.json`]: small,
    [`/org/model/resolve/${REVISION}/model.bin`]: big,
  };
  requests = [];
  honourRange = true;
});

const target = (i: number) => targetOf(models, manifest.models[0]!, manifest.models[0]!.files[i]!);

describe("the first launch's weights", () => {
  it("land in the Hub's cache layout, checked, with refs/main at the pinned revision", async () => {
    assert.equal(missing(models, manifest).length, 2);
    const seen: Progress[] = [];
    await fetchMissing(models, manifest, (progress) => seen.push(progress), baseUrl);
    assert.equal(target(1), join(models, "hub", "models--org--model", "snapshots", REVISION, "model.bin"));
    assert.deepEqual(readFileSync(target(1)), big);
    assert.deepEqual(readFileSync(target(0)), small);
    assert.equal(readFileSync(join(models, "hub", "models--org--model", "refs", "main"), "utf8"), REVISION);
    assert.deepEqual(missing(models, manifest), []);
    assert.equal(seen.at(-1)!.done, totalBytes(manifest));
    assert.equal(seen.at(-1)!.total, totalBytes(manifest));
    const ledger = JSON.parse(readFileSync(join(models, "verified.json"), "utf8")) as Record<string, string>;
    assert.deepEqual(Object.keys(ledger).sort(), [
      join("hub", "models--org--model", "snapshots", REVISION, "config.json"),
      join("hub", "models--org--model", "snapshots", REVISION, "model.bin"),
    ]);
  });

  it("resume a partial download from where it stopped", async () => {
    mkdirSync(dirname(target(1)), { recursive: true });
    writeFileSync(`${target(1)}.part`, big.subarray(0, 120_000));
    await fetchMissing(models, manifest, () => {}, baseUrl);
    assert.deepEqual(requests.find((r) => r.path.endsWith("model.bin"))?.range, "bytes=120000-");
    assert.deepEqual(readFileSync(target(1)), big);
    assert.ok(!existsSync(`${target(1)}.part`));
  });

  it("start a partial download over when the server ignores the range", async () => {
    honourRange = false;
    mkdirSync(dirname(target(1)), { recursive: true });
    writeFileSync(`${target(1)}.part`, Buffer.alloc(120_000, 7));
    await fetchMissing(models, manifest, () => {}, baseUrl);
    assert.deepEqual(readFileSync(target(1)), big);
  });

  it("delete a file whose hash is wrong, and fail naming it", async () => {
    served[`/org/model/resolve/${REVISION}/model.bin`] = Buffer.alloc(big.length, 1);
    await assert.rejects(fetchMissing(models, manifest, () => {}, baseUrl), /org\/model\/model\.bin did not match its checksum/);
    assert.ok(!existsSync(target(1)));
    assert.equal(missing(models, manifest).length, 1, "the good file stays checked");
  });

  it("check a present file again, without downloading it, when the ledger is gone", async () => {
    await fetchMissing(models, manifest, () => {}, baseUrl);
    rmSync(join(models, "verified.json"));
    assert.equal(missing(models, manifest).length, 2);
    requests = [];
    await fetchMissing(models, manifest, () => {}, baseUrl);
    assert.deepEqual(requests, []);
    assert.deepEqual(missing(models, manifest), []);
  });

  it("fail with the status when the Hub refuses a file", async () => {
    delete served[`/org/model/resolve/${REVISION}/config.json`];
    await assert.rejects(fetchMissing(models, manifest, () => {}, baseUrl), /could not download org\/model\/config\.json: HTTP 404/);
  });

  it("are listed in static/weights.json with sizes and hashes for every file", () => {
    const shipped = JSON.parse(readFileSync(join(import.meta.dirname, "..", "static", "weights.json"), "utf8")) as Manifest;
    assert.deepEqual(
      shipped.models.map((m) => m.repo),
      ["Systran/faster-whisper-small.en", "facebook/wav2vec2-lv-60-espeak-cv-ft"],
    );
    for (const model of shipped.models) {
      assert.match(model.revision, /^[0-9a-f]{40}$/);
      for (const file of model.files) {
        assert.match(file.sha256, /^[0-9a-f]{64}$/);
        assert.ok(Number.isInteger(file.size) && file.size > 0);
      }
    }
    assert.equal(totalBytes(shipped), 1_749_635_781);
  });
});
