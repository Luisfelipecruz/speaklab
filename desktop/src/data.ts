// The person's data folder: the cluster, the recordings, the weights, the logs, and the
// two secrets made on the first launch. Nothing in it is shipped; everything in it is
// theirs, and quitting the app leaves it as it was.

import { randomBytes } from "node:crypto";
import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

import type { Secrets } from "./environment.ts";
import type { Paths } from "./layout.ts";

export function ensureFolders(p: Paths): void {
  for (const dir of [dirname(p.cluster), p.audio, p.models, p.logs, p.run]) {
    mkdirSync(dir, { recursive: true, mode: 0o700 });
  }
}

/**
 * The database password and the session-signing key, made once and kept in a file only
 * this account can read. A missing or unreadable file is a first launch: new secrets, and
 * a cluster made with them.
 */
export function loadSecrets(p: Paths): Secrets {
  try {
    const stored = JSON.parse(readFileSync(p.secret, "utf8")) as Partial<Secrets>;
    if (typeof stored.dbPassword === "string" && typeof stored.jwtSecret === "string") {
      return { dbPassword: stored.dbPassword, jwtSecret: stored.jwtSecret };
    }
  } catch {
    // First launch.
  }
  const secrets: Secrets = {
    dbPassword: randomBytes(24).toString("base64url"),
    jwtSecret: randomBytes(32).toString("hex"),
  };
  mkdirSync(dirname(p.secret), { recursive: true, mode: 0o700 });
  writeFileSync(p.secret, `${JSON.stringify(secrets, null, 2)}\n`, { mode: 0o600 });
  chmodSync(p.secret, 0o600);
  return secrets;
}

/** Whether initdb has already made the cluster. */
export function clusterExists(p: Paths): boolean {
  return existsSync(join(p.cluster, "PG_VERSION"));
}

/** A 0600 file holding the database password, for initdb's --pwfile; the caller removes it. */
export function writePasswordFile(p: Paths, secrets: Secrets): string {
  const file = join(p.run, "initdb.pw");
  mkdirSync(p.run, { recursive: true, mode: 0o700 });
  writeFileSync(file, `${secrets.dbPassword}\n`, { mode: 0o600 });
  return file;
}
