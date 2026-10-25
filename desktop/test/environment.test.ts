import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "node:test";

import { baseEnv, databaseUrl, PORTS, postgresEnv, serviceEnv } from "../src/environment.ts";
import { paths, type Service } from "../src/layout.ts";

const p = paths({ resources: "/Applications/SpeakLab.app/Contents/Resources", data: "/Users/someone/Library/Application Support/SpeakLab" });
const base = baseEnv("/Users/someone", "/var/folders/xy/T");
const secrets = { dbPassword: "p@ss/word+=?", jwtSecret: "ab".repeat(32) };
const settings = { whisperThreads: 8 };
const services: Service[] = ["api", "asr", "tts", "pron"];

/** `KEY: ${KEY:-default}` lines under each service's `environment:` in docker-compose.yml. */
function composeEnvironment(): Record<string, Record<string, string>> {
  const compose = readFileSync(join(import.meta.dirname, "..", "..", "docker-compose.yml"), "utf8");
  const found: Record<string, Record<string, string>> = {};
  let service = "";
  let inside = false;
  for (const line of compose.split("\n")) {
    const named = /^ {2}([a-z][a-z-]*):\s*$/.exec(line);
    if (named) {
      service = named[1]!;
      inside = false;
      continue;
    }
    if (/^ {4}environment:\s*$/.test(line)) {
      inside = true;
      found[service] ??= {};
      continue;
    }
    const entry = inside ? /^ {6}([A-Z][A-Z0-9_]*):\s*(.*)$/.exec(line) : null;
    if (entry) {
      const value = entry[2]!.replace(/^"(.*)"$/, "$1");
      found[service]![entry[1]!] = /^\$\{[A-Z_]+:-(.*)\}$/.exec(value)?.[1] ?? value;
    } else if (inside && !/^ {6}/.test(line)) {
      inside = false;
    }
  }
  return found;
}

/** What the desktop gives differently from Compose, on purpose: addresses, paths, secrets. */
const MOVED: Record<Service, string[]> = {
  api: ["DATABASE_URL", "ASR_URL", "TTS_URL", "PRON_URL", "AUDIO_ROOT", "OLLAMA_BASE_URL", "CORS_ORIGINS", "JWT_SECRET"],
  asr: ["HF_HOME", "WHISPER_CPU_THREADS"],
  tts: ["PIPER_VOICE_DIR"],
  pron: ["HF_HOME"],
};

describe("each process's environment", () => {
  it("is built on a clean base, so nothing in the app's own environment reaches a service", () => {
    process.env.SPEAKLAB_LEAK = "1";
    try {
      for (const service of services) {
        const env = serviceEnv(service, base, p, secrets, settings);
        assert.equal(env.SPEAKLAB_LEAK, undefined);
        assert.equal(env.PATH, "/usr/bin:/bin:/usr/sbin:/sbin");
        assert.equal(env.HOME, "/Users/someone");
        assert.equal(env.PYTHONPATH, p.env(service));
        assert.equal(env.PYTHONDONTWRITEBYTECODE, "1", "nothing is written inside the signed bundle");
        assert.equal(env.PYTHONNOUSERSITE, "1");
      }
      assert.equal(postgresEnv(base).SPEAKLAB_LEAK, undefined);
    } finally {
      delete process.env.SPEAKLAB_LEAK;
    }
  });

  it("gives every variable Compose gives the container, with Compose's value unless it is moved", () => {
    const compose = composeEnvironment();
    for (const service of services) {
      const env = serviceEnv(service, base, p, secrets, settings);
      for (const [key, value] of Object.entries(compose[service] ?? {})) {
        assert.ok(key in env, `${service} lacks ${key}`);
        if (!MOVED[service].includes(key)) assert.equal(env[key], value, `${service} ${key}`);
      }
    }
    assert.ok(Object.keys(compose.api ?? {}).length >= 20, "docker-compose.yml was read");
  });

  it("points the API at the app's own Postgres and services, under one host name", () => {
    const env = serviceEnv("api", base, p, secrets, settings);
    assert.equal(env.DATABASE_URL, `postgresql+asyncpg://speaklab:${encodeURIComponent(secrets.dbPassword)}@127.0.0.1:5443/speaklab`);
    assert.equal(databaseUrl(secrets), env.DATABASE_URL);
    assert.equal(env.ASR_URL, "http://127.0.0.1:8111");
    assert.equal(env.TTS_URL, "http://127.0.0.1:8112");
    assert.equal(env.PRON_URL, "http://127.0.0.1:8113");
    assert.equal(env.CORS_ORIGINS, "http://127.0.0.1:3013");
    assert.equal(env.OLLAMA_BASE_URL, "http://127.0.0.1:11434");
    assert.equal(env.AUDIO_ROOT, p.audio);
    assert.equal(env.JWT_SECRET, secrets.jwtSecret);
  });

  it("runs the models offline, on the weights in the data folder", () => {
    const asr = serviceEnv("asr", base, p, secrets, settings);
    assert.equal(asr.HF_HOME, p.models);
    assert.equal(asr.HF_HUB_OFFLINE, "1");
    assert.equal(asr.WHISPER_CPU_THREADS, "8");
    const pron = serviceEnv("pron", base, p, secrets, settings);
    assert.equal(pron.HF_HOME, p.models);
    assert.equal(pron.HF_HUB_OFFLINE, "1");
    assert.equal(pron.NLTK_DATA, p.nltk);
    const tts = serviceEnv("tts", base, p, secrets, settings);
    assert.equal(tts.PIPER_BUILTIN_VOICE_DIR, p.voices);
    assert.equal(serviceEnv("asr", base, p, secrets, { whisperThreads: 6 }).WHISPER_CPU_THREADS, "6");
  });

  it("keeps the ports apart from Compose's, so both can run at once", () => {
    const compose = readFileSync(join(import.meta.dirname, "..", "..", "docker-compose.yml"), "utf8");
    const published = [...compose.matchAll(/"127\.0\.0\.1:(\d+):\d+"/g)].map((m) => Number(m[1]));
    assert.ok(published.length >= 5, "Compose's published ports were read");
    for (const port of Object.values(PORTS)) assert.ok(!published.includes(port), `${port} is Compose's too`);
  });

  it("gives Postgres a fixed time zone, as the image has", () => {
    assert.equal(postgresEnv(base).TZ, "Etc/UTC");
  });
});
