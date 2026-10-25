// What each process is given. Every process starts from a clean base rather than the app's
// own environment, so a variable set in a terminal, a shell profile or Electron itself
// cannot reach a service. The values are the ones docker-compose.yml gives the containers,
// with the addresses moved to 127.0.0.1 and the container paths to the app's folders.

import type { Paths, Service } from "./layout.ts";

/** Fixed, and distinct from Compose's, so the app and the Compose stack can run at once. */
export const PORTS = { web: 3013, api: 8012, asr: 8111, tts: 8112, pron: 8113, postgres: 5443 } as const;

export const HOST = "127.0.0.1";
export const DB_USER = "speaklab";
export const DB_NAME = "speaklab";

export interface Secrets {
  dbPassword: string;
  jwtSecret: string;
}

export interface Settings {
  /** CTranslate2's threads. 0 means 4 to it, which is too few on this Mac. */
  whisperThreads: number;
}

type Env = Record<string, string>;

export function baseEnv(home: string, tmp: string): Env {
  return { PATH: "/usr/bin:/bin:/usr/sbin:/sbin", HOME: home, TMPDIR: tmp, LANG: "C.UTF-8" };
}

function python(base: Env, p: Paths, service: Service): Env {
  return {
    ...base,
    PYTHONPATH: p.env(service),
    // The bundle is signed: bytecode is compiled into it at build time, and nothing is
    // written inside it at run time.
    PYTHONDONTWRITEBYTECODE: "1",
    PYTHONNOUSERSITE: "1",
    HF_HUB_DISABLE_TELEMETRY: "1",
  };
}

export function databaseUrl(secrets: Secrets): string {
  const password = encodeURIComponent(secrets.dbPassword);
  return `postgresql+asyncpg://${DB_USER}:${password}@${HOST}:${PORTS.postgres}/${DB_NAME}`;
}

export function serviceEnv(service: Service, base: Env, p: Paths, secrets: Secrets, settings: Settings): Env {
  const env = python(base, p, service);
  switch (service) {
    case "api":
      return {
        ...env,
        DATABASE_URL: databaseUrl(secrets),
        SQL_ECHO: "0",
        ASR_URL: `http://${HOST}:${PORTS.asr}`,
        TTS_URL: `http://${HOST}:${PORTS.tts}`,
        PRON_URL: `http://${HOST}:${PORTS.pron}`,
        HEALTH_PROBE_TIMEOUT_S: "1.5",
        AUDIO_ROOT: p.audio,
        MAX_UPLOAD_BYTES: "10485760",
        PIPER_VOICE: "en_US-lessac-medium",
        TTS_TIMEOUT_S: "30",
        ASR_TIMEOUT_S: "120",
        OLLAMA_BASE_URL: `http://${HOST}:11434`,
        OLLAMA_MODEL: "gemma4:e4b",
        LLM_TIMEOUT_S: "120",
        LLM_MAX_INPUT_TOKENS: "4000",
        LLM_MAX_OUTPUT_TOKENS: "400",
        // One host name everywhere: the session cookie is SameSite=Lax, and localhost and
        // 127.0.0.1 are two different sites to a browser.
        CORS_ORIGINS: `http://${HOST}:${PORTS.web}`,
        JWT_SECRET: secrets.jwtSecret,
        ACCESS_TOKEN_TTL_HOURS: "168",
        COOKIE_SECURE: "0",
        COOKIE_SAMESITE: "lax",
      };
    case "asr":
      return {
        ...env,
        WHISPER_MODEL: "small.en",
        WHISPER_COMPUTE_TYPE: "int8",
        WHISPER_BEAM_SIZE: "5",
        WHISPER_VAD: "1",
        WHISPER_CPU_THREADS: String(settings.whisperThreads),
        HF_HOME: p.models,
        HF_HUB_OFFLINE: "1",
      };
    case "tts":
      return {
        ...env,
        PIPER_VOICE: "en_US-lessac-medium",
        PIPER_NUM_THREADS: "8",
        PIPER_LENGTH_SCALE: "1.0",
        PIPER_VOICE_DIR: `${p.models}/piper`,
        PIPER_BUILTIN_VOICE_DIR: p.voices,
      };
    case "pron":
      return {
        ...env,
        PRON_MODEL: "facebook/wav2vec2-lv-60-espeak-cv-ft",
        HF_HOME: p.models,
        HF_HUB_OFFLINE: "1",
        NLTK_DATA: p.nltk,
      };
  }
}

/** Postgres and its tools. TZ fixes the cluster's time zone at initdb, as Compose's is. */
export function postgresEnv(base: Env): Env {
  return { ...base, TZ: "Etc/UTC" };
}
