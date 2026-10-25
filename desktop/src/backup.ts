// A backup the honest way: a dump the running server writes itself, and a copy of the
// recordings, in a folder of the person's choosing. Copying the cluster's files while it
// runs would not be one. Restoring is pg_restore into a fresh cluster, written down in the
// README rather than offered as a button.

import { cp, mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { DB_NAME, DB_USER, HOST, PORTS, postgresEnv, type Secrets } from "./environment.ts";
import type { Paths } from "./layout.ts";
import { runOnce } from "./processes.ts";

/** "2026-10-25 14-30" in the Mac's own time zone: a folder name, so no colon. */
export function stampOf(now: Date): string {
  const two = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${two(now.getMonth() + 1)}-${two(now.getDate())} ${two(now.getHours())}-${two(now.getMinutes())}`;
}

export async function backup(
  p: Paths,
  base: Record<string, string>,
  secrets: Secrets,
  into: string,
  version: string,
  now = new Date(),
): Promise<string> {
  const folder = join(into, `SpeakLab backup ${stampOf(now)}`);
  await mkdir(folder, { recursive: false });
  const client = { cwd: folder, env: { ...postgresEnv(base), PGPASSWORD: secrets.dbPassword } };
  const address = ["-h", HOST, "-p", String(PORTS.postgres), "-U", DB_USER];
  const revision = await runOnce({
    file: p.pg("psql"),
    args: [...address, "-d", DB_NAME, "-tAX", "-c", "SELECT version_num FROM alembic_version"],
    ...client,
  });
  if (revision.code !== 0) throw new Error(`the schema revision could not be read: ${revision.output.trim() || `exit ${revision.code}`}`);
  const dump = await runOnce({ file: p.pg("pg_dump"), args: [...address, "-Fc", "-f", join(folder, "speaklab.dump"), DB_NAME], ...client }, 600_000);
  if (dump.code !== 0) throw new Error(`pg_dump failed: ${dump.output.trim() || `exit ${dump.code}`}`);
  await cp(p.audio, join(folder, "audio"), { recursive: true });
  const about = {
    app: "SpeakLab",
    version,
    schema: revision.output.trim(),
    made: now.toISOString(),
    database: "speaklab.dump: pg_dump -Fc of the app's database, PostgreSQL 16",
    recordings: "audio/: every recording, by account and content hash",
  };
  await writeFile(join(folder, "backup.json"), `${JSON.stringify(about, null, 2)}\n`);
  return folder;
}
