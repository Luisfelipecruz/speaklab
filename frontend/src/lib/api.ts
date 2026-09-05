/**
 * The one place that knows the API's address, its shapes, and how it fails.
 *
 * Two base URLs, because there are two callers. A server component runs inside the
 * compose network and resolves `api:8000`; the browser runs on the host and resolves
 * `localhost:8002`. Using one for both is the classic Next.js-in-a-container bug: it
 * works in `npm run dev` on the host and fails the moment it is containerised, or the
 * other way round.
 *
 * **The types below are hand-written mirrors of `api/models/*.py`, and that is a
 * decision with a cost.** Generating them from the OpenAPI document would keep them in
 * step automatically, and at m12 it may be worth it. At m7 it would add a code
 * generator, a checked-in artefact and a "is the schema stale?" question to every
 * review, to keep six interfaces honest — and the interfaces are covered by the one
 * thing generation cannot give you either way, which is a test that calls the real API.
 * What is written here is only the subset the UI reads: `TurnOut.words` exists on the
 * server and is deliberately not serialised (see `api/models/turn.py`), and nothing
 * here should grow a field the screens do not draw.
 */

export const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL ?? "http://localhost:8002";

export const PUBLIC_API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8002";

/** Closed vocabulary, mirroring api/routers/health.py. */
export type ServiceStatus = "ok" | "unreachable" | "error";

export interface ProbeResult {
  status: ServiceStatus;
  url?: string;
  latency_ms?: number;
  detail?: string;
  /** The service's own body. `model_loaded: false` while weights are still downloading. */
  reports?: Record<string, unknown>;
}

export interface Health {
  status: "ok" | "degraded" | "unavailable";
  version: string;
  database: { status: string; latency_ms?: number; detail?: string };
  models: Record<string, ProbeResult>;
}

// ── Failure ─────────────────────────────────────────────────────────────────

/**
 * A failed request, carrying the status so a caller can tell 401 from 409.
 *
 * Status `0` is reserved for "never answered" — a network-level failure, DNS, CORS
 * rejecting before the request left, or the API container simply not running. It is a
 * different thing from a 500 and the UI says so differently: one is "start the stack",
 * the other is "this is a bug".
 */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** True when nothing answered at all. */
  get unreachable(): boolean {
    return this.status === 0;
  }
}

/**
 * Turn an error body into one sentence a person can act on.
 *
 * FastAPI answers with two different shapes and they have to be told apart. A raised
 * `HTTPException` gives `{detail: "Incorrect email or password"}`; a validation failure
 * gives `{detail: [{loc, msg, type}, ...]}`. Rendering the second one as-is puts
 * `[object Object]` or a JSON array in front of the user, which is the most common way
 * a FastAPI frontend leaks its own internals into the interface.
 */
export function messageFrom(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { loc?: unknown[]; msg?: string };
    // `loc` is ["body", "password"]; the field name is the part worth showing.
    const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : undefined;
    const message = first.msg ?? "is not valid";
    return field ? `${String(field)}: ${message}` : message;
  }

  return `Request failed (${status})`;
}

/**
 * One browser request, with the session cookie attached and errors normalised.
 *
 * `credentials: "include"` is the whole design of the auth story and it is set here so
 * no caller has to remember it. The token is in an httpOnly cookie: this module cannot
 * read it, cannot attach it to a header, and cannot store it — it can only ask the
 * browser to send it. Omitting the flag is the failure this function prevents, because
 * `fetch` drops cross-origin cookies by default and a login would appear to succeed
 * while every following request 401s, with nothing in the console to say why.
 *
 * **The Content-Type is not set for a FormData body.** The browser has to write that
 * header itself, because only it knows the multipart boundary it generated; setting
 * `multipart/form-data` by hand produces a body the server cannot parse and a 422 that
 * looks like the file was rejected.
 */
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;

  let response: Response;
  try {
    response = await fetch(`${PUBLIC_API_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: isForm
        ? { ...init.headers }
        : { "Content-Type": "application/json", ...init.headers },
    });
  } catch {
    throw new ApiError("Could not reach the API. Is the stack running?", 0);
  }

  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(messageFrom(body, response.status), response.status);
  return body as T;
}

// ── Health ──────────────────────────────────────────────────────────────────

/**
 * Fetch /health, or `null` if the API itself cannot be reached.
 *
 * `null` is a third state and not an error: it is what the page shows when the API
 * container is not running, which is different from the API running and reporting that
 * something else is down. Throwing here would render an error boundary that says less.
 *
 * `cache: "no-store"` because a cached health check is not a health check.
 */
export async function getHealth(): Promise<Health | null> {
  try {
    const response = await fetch(`${INTERNAL_API_URL}/health`, {
      cache: "no-store",
    });
    // 503 is a real answer — the API is up and telling us the database is gone — so it
    // is parsed rather than treated as unreachable.
    return (await response.json()) as Health;
  } catch {
    return null;
  }
}

// ── Scenarios ───────────────────────────────────────────────────────────────

export type CefrBand = "A1" | "A2" | "B1" | "B2" | "C1" | "C2";

export const CEFR_ORDER: readonly CefrBand[] = ["A1", "A2", "B1", "B2", "C1", "C2"];

export interface ScenarioSummary {
  slug: string;
  title: string;
  description: string;
  category: string;
  cefr_band: CefrBand;
  target_grammar: string[];
  target_functions: string[];
}

/**
 * One scenario, opened. `persona_prompt` is absent here because it is absent from the
 * response — deliberately, and asserted by a server-side test. It is the exercise: a
 * user who has read the interviewer's instructions is no longer practising the thing
 * the scenario was built to make them practise.
 */
export interface ScenarioDetail extends ScenarioSummary {
  goal: string;
  rubric: {
    criteria?: { name: string; descriptor: string }[];
    min_turns?: number;
  };
}

export function listScenarios(params: {
  band?: string;
  category?: string;
  target_grammar?: string;
} = {}): Promise<ScenarioSummary[]> {
  return request<ScenarioSummary[]>(`/scenarios${queryString(params)}`);
}

export function getScenario(slug: string): Promise<ScenarioDetail> {
  return request<ScenarioDetail>(`/scenarios/${encodeURIComponent(slug)}`);
}

// ── Turns and sessions ──────────────────────────────────────────────────────

export interface Turn {
  id: number;
  idx: number;
  role: "user" | "assistant";
  transcript: string | null;
  audio_asset_id: number | null;
  /** A path, not a URL: `/audio/12`. Run it through `audioUrl` before an <audio src>. */
  audio_url: string | null;
  asr_confidence: number | null;
  asr_model: string | null;
  llm_model: string | null;
  tts_voice: string | null;
  latency_ms: number | null;
  created_at: string;
  /**
   * Below PRD §7.5's gate, derived server-side from `asr_confidence` so the threshold
   * lives in one language. It is on the turn and not only on the response that created
   * it because a reloaded transcript has to mark the same turns as the live one did.
   */
  low_confidence: boolean;
}

/**
 * Whether the reply was actually spoken, and if not, why.
 *
 * A separate object rather than a nullable audio URL, because "the voice is down" and
 * "this turn has no audio" are different facts. `TurnBubble` renders the difference: a
 * missing player is a bug, a player replaced by a note saying the voice is unavailable
 * is a system being honest.
 */
export interface Speech {
  status: "ok" | "skipped" | "unavailable" | "rejected" | "protocol";
  detail: string | null;
  voice: string | null;
  duration_ms: number | null;
  sample_rate: number | null;
  sentences: number;
}

export interface TurnTiming {
  total_ms: number;
  asr_ms: number;
  generation_ms: number;
  /** The tail, not the work: most synthesis happened inside generation. See decision 0003. */
  synthesis_ms: number;
  reply_ms: number;
  model_load_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
}

export interface TurnResponse {
  session_id: number;
  user_turn: Turn;
  reply_turn: Turn;
  speech: Speech;
  timing: TurnTiming;
  /** Below PRD §7.5's gate. Still stored, still replied to, must not count towards a trend. */
  low_confidence: boolean;
}

export interface SessionSummary {
  id: number;
  scenario_slug: string | null;
  scenario_title: string | null;
  mode: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  turn_count: number;
}

/**
 * The report FR-9 produces, split by **where each number came from**.
 *
 * The nesting is invariant I1 made structural rather than documented: `measured` is
 * counted from stored rows and is the same on every rebuild, `narrative` is written by
 * a language model, and `pending` names the parts that need analysers which do not
 * exist yet. A caller has to reach through a key called `narrative` to get at a
 * judgement, which is the point — flattening them is one refactor away from plotting a
 * model's opinion on a trend chart.
 */
export interface SessionReportShape {
  schema: number;
  scenario: string | null;
  goal: string | null;
  measured: {
    turns: { total: number; user: number; assistant: number };
    duration_ms: number;
    words_spoken: number;
    mean_asr_confidence: number | null;
    median_turn_latency_ms: number | null;
    reached_min_turns: boolean | null;
    min_turns: number | null;
  };
  narrative:
    | ({ status: "ok"; by: string; model: string; summary: string; goal_met: boolean | null; note: string })
    | ({ status: "skipped" | "unavailable" | "unparseable"; detail?: string; model?: string })
    | null;
  pending: Record<string, string>;
}

export interface SessionDetail extends SessionSummary {
  turns: Turn[];
  report: SessionReportShape | null;
}

export interface SessionPage {
  items: SessionSummary[];
  total: number;
  limit: number;
  offset: number;
}

export function startSession(scenarioSlug: string): Promise<SessionDetail> {
  return request<SessionDetail>("/sessions", {
    method: "POST",
    body: JSON.stringify({ scenario_slug: scenarioSlug }),
  });
}

export function getSession(id: number): Promise<SessionDetail> {
  return request<SessionDetail>(`/sessions/${id}`);
}

export function listSessions(params: { limit?: number; offset?: number } = {}): Promise<SessionPage> {
  return request<SessionPage>(`/sessions${queryString(params)}`);
}

export function endSession(id: number): Promise<SessionDetail> {
  return request<SessionDetail>(`/sessions/${id}/end`, { method: "POST" });
}

export function deleteSession(id: number): Promise<void> {
  return request<void>(`/sessions/${id}`, { method: "DELETE" });
}

/**
 * Send one recorded turn. FR-7.
 *
 * The field name is `file` because that is what `add_turn` declares; a `FormData` key
 * that does not match produces a 422 naming a missing field, which reads like the
 * recording was rejected. The filename carries the container so the recogniser has a
 * hint before it sniffs the bytes — Chrome sends WebM, Safari sends MP4, and neither
 * should have to be guessed at twice.
 */
export function postTurn(
  sessionId: number,
  audio: Blob,
  filename = "turn.webm",
): Promise<TurnResponse> {
  const form = new FormData();
  form.append("file", audio, filename);
  return request<TurnResponse>(`/sessions/${sessionId}/turns`, {
    method: "POST",
    body: form,
  });
}

// ── Small helpers ───────────────────────────────────────────────────────────

/**
 * Absolute URL for a stored recording.
 *
 * The API returns `/audio/12` rather than a full URL, because the host it is reachable
 * on depends on who is asking — and the browser is the only caller that ever puts one
 * in an `<audio src>`. Assembling the path here rather than in each component is what
 * keeps the scheme in one language instead of two that drift apart at the first rename.
 */
export function audioUrl(path: string | null): string | null {
  if (!path) return null;
  return path.startsWith("http") ? path : `${PUBLIC_API_URL}${path}`;
}

function queryString(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

// ── Read-aloud (m8) ─────────────────────────────────────────────────────────

export interface PassageSummary {
  slug: string;
  title: string;
  cefr_band: CefrBand;
  /** ARPAbet symbols this passage was engineered to force, e.g. ["TH"]. */
  phoneme_focus: string[];
  word_count: number;
}

export interface PassageDetail extends PassageSummary {
  body: string;
}

export interface PhonemeScore {
  word: string;
  word_idx: number;
  phone_idx: number;
  canonical_phone: string;
  /**
   * What won the segment instead, or null. The null is invariant I2 in a field: where
   * nothing clearly won, the interface must not name a sound the model did not assert.
   */
  recognized_phone: string | null;
  start_ms: number | null;
  end_ms: number | null;
  /** <= 0 by construction. 0 means the target phone was itself the best-scoring one. */
  gop: number;
  posterior: number | null;
}

export interface PronunciationSummary {
  phones: number;
  mean_gop: number | null;
  median_gop: number | null;
  /** This reading's own 5th percentile — not a calibrated threshold. See handoff Q2. */
  percentile_5: number | null;
  r_composites: number;
  blank_dominated: number;
}

export type AttemptStatus = "pending" | "scoring" | "scored" | "failed";

export interface AttemptSummary {
  id: number;
  session_id: number;
  passage_id: number;
  passage_slug: string | null;
  passage_title: string | null;
  status: AttemptStatus;
  transcript: string | null;
  /** Word error rate against the passage. Above ~0.5 the phone scores are noise. */
  wer: number | null;
  error_message: string | null;
  scored_at: string | null;
  created_at: string;
  audio_url: string | null;
  phoneme_count: number;
}

export interface AttemptDetail extends AttemptSummary {
  passage_body: string | null;
  phonemes: PhonemeScore[];
  summary: PronunciationSummary | null;
  /**
   * Whether there are phone scores to show, and if not, why — separate from `status`
   * because "processed, with the scorer switched off" is not a failed reading (PRD R6).
   */
  pronunciation: "ok" | "unavailable";
  pronunciation_detail: string | null;
}

export interface AttemptPage {
  items: AttemptSummary[];
  total: number;
  limit: number;
  offset: number;
}

export function listPassages(
  params: { band?: string; phoneme_focus?: string } = {},
): Promise<PassageSummary[]> {
  return request<PassageSummary[]>(`/passages${queryString(params)}`);
}

export function getPassage(slug: string): Promise<PassageDetail> {
  return request<PassageDetail>(`/passages/${slug}`);
}

/**
 * Send one reading. FR-12.
 *
 * Answers in about as long as a conversational turn — the recogniser runs inside the
 * request because the stored recording's row cannot be written without a decoder's
 * account of the file — and comes back `pending`, with the phones still being aligned.
 * `getAttempt` is the poll.
 */
export function postAttempt(
  passageSlug: string,
  audio: Blob,
  filename = "reading.webm",
  sessionId?: number,
): Promise<AttemptDetail> {
  const form = new FormData();
  form.append("file", audio, filename);
  form.append("passage_slug", passageSlug);
  if (sessionId !== undefined) form.append("session_id", String(sessionId));
  return request<AttemptDetail>("/attempts", { method: "POST", body: form });
}

export function getAttempt(id: number): Promise<AttemptDetail> {
  return request<AttemptDetail>(`/attempts/${id}`);
}

export function listAttempts(
  params: {
    passage_slug?: string;
    session_id?: number;
    limit?: number;
    offset?: number;
  } = {},
): Promise<AttemptPage> {
  return request<AttemptPage>(`/attempts${queryString(params)}`);
}

/** Score a stored reading again. FR-16 — the recording is still on disk. */
export function rescoreAttempt(id: number): Promise<AttemptDetail> {
  return request<AttemptDetail>(`/attempts/${id}/rescore`, { method: "POST" });
}

/**
 * The worst GOP recorded for each word of a reading, by word index.
 *
 * **The worst, not the mean, and the choice is the whole point of the heatmap.** A word
 * is mispronounced if any sound in it was, and averaging /θ/ at −9 with four correct
 * phones at 0 gives −1.8, which is indistinguishable from a word that was merely a
 * little unclear throughout. The learner needs to find the word with the broken sound in
 * it, so the map carries the broken sound's score.
 */
export function worstByWord(phonemes: PhonemeScore[]): Map<number, PhonemeScore> {
  const worst = new Map<number, PhonemeScore>();
  for (const phone of phonemes) {
    const current = worst.get(phone.word_idx);
    if (!current || phone.gop < current.gop) worst.set(phone.word_idx, phone);
  }
  return worst;
}

/**
 * The confusion pairs in a reading: canonical phone, what was heard instead, how often.
 *
 * PRD §7.4's `/θ/ → /s/ ×34`. Counted only where the two differ *and* the score is below
 * `floor`, because a phone realised acceptably still has a `recognized_phone` — often
 * the same sound written differently — and listing those would bury the two rows that
 * matter under two hundred that do not.
 */
export function confusionPairs(
  phonemes: PhonemeScore[],
  floor: number,
): { canonical: string; heard: string; count: number; worst: number }[] {
  const tally = new Map<string, { canonical: string; heard: string; count: number; worst: number }>();
  for (const phone of phonemes) {
    if (phone.gop >= floor || !phone.recognized_phone) continue;
    const canonical = phone.canonical_phone.replace(/[0-2]$/, "");
    const key = `${canonical}→${phone.recognized_phone}`;
    const row = tally.get(key);
    if (row) {
      row.count += 1;
      row.worst = Math.min(row.worst, phone.gop);
    } else {
      tally.set(key, {
        canonical,
        heard: phone.recognized_phone,
        count: 1,
        worst: phone.gop,
      });
    }
  }
  return [...tally.values()].sort((a, b) => b.count - a.count || a.worst - b.worst);
}
