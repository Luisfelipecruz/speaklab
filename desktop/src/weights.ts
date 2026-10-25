// The speech weights, fetched once on the first launch, at pinned revisions, each file
// checked against its SHA-256 before it is used. They land in the layout Hugging Face's
// own cache uses, with refs/main naming the pinned revision, so the services find them
// offline exactly as they find the files the containers downloaded: nothing in the
// services knows the app exists.

import { createHash } from "node:crypto";
import { createReadStream, createWriteStream, existsSync, mkdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";

export interface WeightFile {
  path: string;
  size: number;
  sha256: string;
}

export interface WeightModel {
  repo: string;
  revision: string;
  files: WeightFile[];
}

export interface Manifest {
  models: WeightModel[];
}

export interface Wanted {
  model: WeightModel;
  file: WeightFile;
  target: string;
}

export function modelDir(models: string, repo: string): string {
  return join(models, "hub", `models--${repo.replace("/", "--")}`);
}

export function targetOf(models: string, model: WeightModel, file: WeightFile): string {
  return join(modelDir(models, model.repo), "snapshots", model.revision, file.path);
}

export function totalBytes(manifest: Manifest): number {
  return manifest.models.reduce((sum, m) => sum + m.files.reduce((s, f) => s + f.size, 0), 0);
}

/** Files whose SHA-256 has been checked since they were written, by their path under `models`. */
function ledgerPath(models: string): string {
  return join(models, "verified.json");
}

function readLedger(models: string): Record<string, string> {
  try {
    return JSON.parse(readFileSync(ledgerPath(models), "utf8")) as Record<string, string>;
  } catch {
    return {};
  }
}

/** Everything that is absent, the wrong size, or not checked against its hash yet. */
export function missing(models: string, manifest: Manifest): Wanted[] {
  const ledger = readLedger(models);
  const wanted: Wanted[] = [];
  for (const model of manifest.models) {
    for (const file of model.files) {
      const target = targetOf(models, model, file);
      const present = existsSync(target) && statSync(target).size === file.size;
      if (!present || ledger[relative(models, target)] !== file.sha256) wanted.push({ model, file, target });
    }
  }
  return wanted;
}

async function sha256Of(path: string): Promise<string> {
  const hash = createHash("sha256");
  await pipeline(createReadStream(path), hash);
  return hash.digest("hex");
}

export interface Progress {
  done: number;
  total: number;
  file: string;
}

/**
 * Fetches what `missing` lists. A partial download is kept as `<file>.part` and resumed
 * with a Range request; a file whose hash is wrong is deleted and the fetch fails, naming
 * it. Ends by pointing each model's refs/main at its pinned revision.
 */
export async function fetchMissing(
  models: string,
  manifest: Manifest,
  onProgress: (p: Progress) => void,
  baseUrl = "https://huggingface.co",
): Promise<void> {
  const total = totalBytes(manifest);
  const wanted = missing(models, manifest);
  let done = total - wanted.reduce((sum, w) => sum + w.file.size, 0);
  const ledger = readLedger(models);
  for (const { model, file, target } of wanted) {
    const label = `${model.repo}/${file.path}`;
    mkdirSync(dirname(target), { recursive: true });
    const present = existsSync(target) && statSync(target).size === file.size;
    if (!present) {
      const part = `${target}.part`;
      let start = existsSync(part) ? statSync(part).size : 0;
      if (start > file.size) {
        rmSync(part);
        start = 0;
      }
      if (start < file.size) {
        const url = `${baseUrl}/${model.repo}/resolve/${model.revision}/${file.path}`;
        const response = await fetch(url, { headers: start > 0 ? { Range: `bytes=${start}-` } : {} });
        if (start > 0 && response.status !== 206) start = 0;
        if (!response.ok || !response.body) throw new Error(`could not download ${label}: HTTP ${response.status}`);
        let received = start;
        const counter = new Transform({
          transform(chunk: Buffer, _encoding, callback) {
            received += chunk.length;
            onProgress({ done: done + received, total, file: label });
            callback(null, chunk);
          },
        });
        await pipeline(
          Readable.fromWeb(response.body as import("node:stream/web").ReadableStream),
          counter,
          createWriteStream(part, { flags: start > 0 ? "a" : "w" }),
        );
      }
      renameSync(part, target);
    }
    const actual = await sha256Of(target);
    if (actual !== file.sha256) {
      rmSync(target, { force: true });
      throw new Error(`${label} did not match its checksum (got ${actual.slice(0, 12)}…); it was deleted`);
    }
    ledger[relative(models, target)] = file.sha256;
    writeFileSync(ledgerPath(models), `${JSON.stringify(ledger, null, 2)}\n`);
    done += file.size;
    onProgress({ done, total, file: label });
  }
  for (const model of manifest.models) {
    const refs = join(modelDir(models, model.repo), "refs");
    mkdirSync(refs, { recursive: true });
    writeFileSync(join(refs, "main"), model.revision);
  }
}
