// Where everything is: what the app ships (read-only, inside the signed bundle) and what
// it keeps (the person's data folder). Nothing here touches the disk.

import { join } from "node:path";

export type Service = "api" | "asr" | "tts" | "pron" | "asr-multi";

/** asr-multi is asr's code and environment, given another model. */
function codeOf(service: Service): Exclude<Service, "asr-multi"> {
  return service === "asr-multi" ? "asr" : service;
}

export interface Layout {
  /** Contents/Resources in the packaged app; desktop/.build/stage in a development run. */
  resources: string;
  /** userData: ~/Library/Application Support/SpeakLab in the packaged app. */
  data: string;
}

export interface Paths {
  python: string;
  env(service: Service): string;
  source(service: Service): string;
  pg(tool: "initdb" | "postgres" | "pg_isready" | "createdb" | "psql" | "pg_dump" | "pg_restore"): string;
  voices: string;
  nltk: string;
  web: string;
  cluster: string;
  audio: string;
  models: string;
  logs: string;
  run: string;
  secret: string;
}

export function paths({ resources, data }: Layout): Paths {
  return {
    python: join(resources, "python", "bin", "python3.12"),
    env: (service) => join(resources, "envs", codeOf(service)),
    source: (service) =>
      service === "api" ? join(resources, "src", "api") : join(resources, "src", "infra", codeOf(service)),
    pg: (tool) => join(resources, "pg", "bin", tool),
    voices: join(resources, "voices"),
    nltk: join(resources, "nltk_data"),
    web: join(resources, "web"),
    cluster: join(data, "postgres", "16"),
    audio: join(data, "audio"),
    models: join(data, "models"),
    logs: join(data, "logs"),
    run: join(data, "run"),
    secret: join(data, "secret.json"),
  };
}
