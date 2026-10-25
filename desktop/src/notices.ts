// What the app says to the person, in words: about the language model, which runs on the
// Mac rather than in the app, and about a part of the app that failed. Nothing here knows
// Electron, so all of it is tested.

export interface LlmReport {
  status?: string;
  detail?: string;
}

/** Nothing when conversations work on the measured build; otherwise what is wrong, and what to do. */
export function llmNotice(llm: LlmReport | undefined): string | undefined {
  if (!llm || llm.status === "ok") return undefined;
  if (llm.status === "unreachable") {
    return "Conversations need Ollama, and nothing answers on 127.0.0.1:11434. Open Ollama (or install it from ollama.com), then check again.";
  }
  if (llm.status === "degraded") return `Conversations work. ${llm.detail ?? "The model is not the build the published figures were measured on."}`;
  return llm.detail ?? `The language model is ${llm.status}.`;
}

/** Each unit as the person meets it, in lower case so that it can sit inside a sentence. */
const NAMES: Record<string, string> = {
  initdb: "creating the database",
  postgres: "the database",
  createdb: "naming the database",
  migrate: "updating the database's tables",
  seed: "adding the practice material",
  api: "SpeakLab's service",
  asr: "speech recognition",
  tts: "the voice",
  pron: "pronunciation scoring",
};

export function nameOf(unit: string): string {
  return NAMES[unit] ?? unit;
}

/** A unit's name at the head of a line. */
export function labelOf(unit: string): string {
  const name = nameOf(unit);
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/** The supervisor's own wording, which needs the unit's name before it to be a sentence. */
const BARE = /^(exited|was not ready|needs )/;

export interface UnitState {
  state: string;
  detail?: string;
}

/**
 * What failed, one sentence per line. A unit that failed only because something it needs
 * failed is left out when the cause is there to be named; a job's own explanation is
 * already a sentence and is said as it is.
 */
export function describeFailures(units: Record<string, UnitState>): string {
  const failed = Object.entries(units).filter(([, unit]) => unit.state === "failed");
  const causes = failed.filter(([, unit]) => !unit.detail?.startsWith("needs "));
  return (causes.length > 0 ? causes : failed)
    .map(([name, { detail }]) => {
      if (detail && !BARE.test(detail)) return detail;
      const what = detail?.startsWith("needs ")
        ? `needs ${detail.slice("needs ".length).split(", ").map(nameOf).join(" and ")}`
        : (detail ?? "failed");
      return `${labelOf(name)} ${what}.`;
    })
    .join("\n");
}
