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
 * step automatically, and may eventually be worth it. Today it would add a code
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
   * Below the confidence gate, derived server-side from `asr_confidence` so the
   * threshold lives in one language. It is on the turn and not only on the response that created
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
  /** Below the confidence gate. Still stored, still replied to, never counted in a trend. */
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
 * The end-of-session report, split by **where each number came from**.
 *
 * The nesting is structural rather than documented: `measured` is
 * counted from stored rows and is the same on every rebuild, `narrative` is written by
 * a language model, and `pending` names the parts that need analysers which do not
 * exist yet. A caller has to reach through a key called `narrative` to get at a
 * judgement, which is the point — flattening them is one refactor away from plotting a
 * model's opinion on a trend chart.
 */
/**
 * One correction, as the report carries it.
 *
 * `counted` is not decoration and not derivable here: an error can be shown and still be
 * kept out of every rate, either because the recogniser was unsure of the words under it
 * or because the model that proposed it hedged. The API decides which; the UI renders the
 * difference rather than recomputing it against a threshold it would have to duplicate.
 */
export interface LanguageErrorItem {
  turn_id: number;
  category: string;
  subcategory: string | null;
  span_start: number | null;
  span_end: number | null;
  original: string;
  correction: string;
  explanation: string | null;
  confidence: number;
  asr_suspect: boolean;
  counted: boolean;
  /**
   * Which detector proposed it: grammar rules read from the parse, or the language model.
   * Absent on a report written before the rules existed, when every row was the model's.
   */
  detector?: "llm" | "rule";
  /**
   * The verb form the corrected words were said in, and the one the correction needs.
   * Null on a side with no finite form, and on both for a correction that is not of a
   * verb's form. Absent on a report written before corrections were joined to forms.
   */
  form?: string | null;
  corrected_form?: string | null;
}

/** How one verb form was used: said, said wrongly, and needed where it was not said. */
export interface FormAccuracy {
  used: number;
  right: number;
  wrong: number;
  missed: number;
  /** Right over used plus missed. Null where too few to give as a proportion. */
  accuracy: number | null;
}

export interface SessionAnalysis {
  /** False when the report was written before every turn had been analysed. */
  complete: boolean;
  turns_analysed: number;
  turns_outstanding: number;
  fluency: {
    words_spoken: number;
    speech_rate_wpm: number | null;
    articulation_rate_wpm: number | null;
    pause_ratio: number | null;
    mean_length_run: number | null;
    filler_count: number;
    fillers_per_100_words: number;
    mean_pause_before_speaking_ms: number | null;
  } | null;
  grammar_usage: Record<string, number>;
  target_forms: { declared: string[]; elicited: string[]; not_elicited: string[] };
  /** Per verb form. Absent on a report written before corrections were joined to forms. */
  form_accuracy?: Record<string, FormAccuracy>;
  errors: {
    total: number;
    counted: number;
    asr_suspect: number;
    low_confidence: number;
    per_100_words: number | null;
    by_category: Record<string, number>;
    items: LanguageErrorItem[];
    /** Rows per detector. Absent on a report written before the rules existed. */
    by_detector?: Record<string, number>;
    rejected: number;
    /** The model's proposals a rule had already made, which are not stored twice. */
    superseded?: number;
    rejection_rate: number | null;
    rejected_reasons: Record<string, number>;
  };
}

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
  /** Null on a report written before the analysers existed. */
  analysis?: SessionAnalysis | null;
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
 * Send one recorded turn.
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

// ── Read-aloud ──────────────────────────────────────────────────────────────

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
   * What won the segment instead, or null. The null matters: where nothing clearly won,
   * the interface must not name a sound the model did not assert.
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
  /** This reading's own 5th percentile — not a calibrated threshold. */
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
   * because "processed, with the scorer switched off" is not a failed reading.
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
 * Send one reading.
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

/** Score a stored reading again — the recording is still on disk. */
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
 * Rendered as `/θ/ → /s/ ×34`. Counted only where the two differ *and* the score is below
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

// ── Progress ────────────────────────────────────────────────────────────────

/**
 * Whether a series may be drawn, and what it is waiting for.
 *
 * `shown: false` is not an error and not an empty result — it is the ordinary state of a
 * new account, and the reason is written for the person reading the page rather than for
 * a developer reading a log. A chart that silently omits thin data looks exactly like a
 * speaker who did not practise, which is the one wrong impression this page must not give.
 */
export interface Gate {
  shown: boolean;
  reason: string | null;
  have: number;
  need: number;
}

/**
 * One period's value, or a hole with a reason.
 *
 * A hole is kept in the array rather than dropped, so a fortnight of silence occupies
 * the width it actually occupied. Dropping it would close the gap and draw two distant
 * points as consecutive practice.
 */
export interface TrendPoint {
  start: string;
  value: number | null;
  samples: number;
  withheld: string | null;
}

/**
 * One metric over the window.
 *
 * `better` is the field that decides whether this series is allowed an opinion. Most
 * fluency measures have no better end — faster is nerves as often as it is fluency — so
 * they arrive with `better: null` and `direction: null`, and the component renders numbers
 * without a verdict. That absence is the design, not a gap to be filled in later.
 */
export interface TrendSeries {
  metric: string;
  label: string;
  unit: string | null;
  better: "higher" | "lower" | null;
  points: TrendPoint[];
  gate: Gate;
  change: number | null;
  direction: "improving" | "slipping" | "flat" | null;
}

export interface MetricFamily {
  name: string;
  label: string;
  description: string;
  series: TrendSeries[];
  /** Anything needed to read this family honestly. Only accuracy carries one. */
  caveat: string | null;
}

/** One sound, against this speaker's own recent readings rather than against anybody else. */
export interface PhoneTrend {
  phone: string;
  mean_gop: number;
  z: number | null;
  baseline_mean: number | null;
  baseline_readings: number;
  samples: number;
}

export interface Repertoire {
  latest_period: string | null;
  forms: Record<string, number>;
  distinct_forms: number;
  previous_distinct_forms: number | null;
  /** Per verb form, in the same period as `forms`. The page shows the counts only. */
  accuracy: Record<string, FormAccuracy>;
  /** Times a form was said or needed before the API gives `accuracy` as a proportion. */
  accuracy_floor: number;
  /** What the accuracy is counted from and how far to trust it. Set when there is any. */
  caveat: string | null;
  /** Set when the range of forms narrowed while the error rate also fell. */
  warning: string | null;
}

export interface ProgressTotals {
  sessions: number;
  turns: number;
  words: number;
  attempts: number;
  phones: number;
  periods: number;
}

export interface Progress {
  period: string;
  since: string;
  until: string;
  totals: ProgressTotals;
  families: MetricFamily[];
  phones: PhoneTrend[];
  phone_gate: Gate;
  repertoire: Repertoire;
  /** Something was analysed or scored after the last rollup. The page offers a refresh. */
  stale: boolean;
}

export interface Recommendation {
  kind: "error_category" | "weak_phone" | "unused_form" | "practise";
  title: string;
  reason: string;
  measured: number | null;
  samples: number;
  score: number;
  scenario_slug: string | null;
  passage_slug: string | null;
}

export interface Recommendations {
  items: Recommendation[];
  confidence: "none" | "low" | "moderate" | "good";
  detail: string | null;
}

// ── The grammar page ────────────────────────────────────────────────────────

/** One correction, in the sentence it was made in. */
export interface CorrectionExample {
  id: number;
  session_id: number;
  turn_id: number;
  said_at: string;
  scenario_title: string | null;
  /**
   * The sentence around the correction, from the transcript. `quote` is the transcript's
   * own words under it; null when they could not be placed, and then the sentence is
   * empty and the correction is shown on its own.
   */
  before: string;
  quote: string | null;
  after: string;
  original: string;
  correction: string;
  explanation: string | null;
  subcategory: string | null;
  detector: "llm" | "rule";
  counted: boolean;
  asr_suspect: boolean;
  form: string | null;
  corrected_form: string | null;
}

export interface CategoryCorrections {
  category: string;
  label: string;
  description: string;
  counted: number;
  /** Shown and not counted: a possible mishearing, or hedged by the model. */
  not_counted: number;
  per_100_words: number | null;
  by_detector: Record<string, number>;
  /** The newest few; `counted + not_counted` covers them all. */
  examples: CorrectionExample[];
}

export interface FormCorrection {
  id: number;
  session_id: number;
  original: string;
  correction: string;
  form: string | null;
  corrected_form: string | null;
}

/** One verb form: said, said wrongly, needed where another was said. No proportion. */
export interface FormPractice {
  form: string;
  label: string;
  used: number;
  right: number;
  wrong: number;
  missed: number;
  corrections: FormCorrection[];
}

export interface WeakestForm {
  form: string;
  label: string;
  used: number;
  right: number;
  wrong: number;
  missed: number;
  reason: string;
  scenario_slug: string | null;
  scenario_title: string | null;
}

export interface GrammarPage {
  since: string;
  until: string;
  totals: { sessions: number; turns: number; words: number; corrections: number; counted: number };
  categories: CategoryCorrections[];
  forms: FormPractice[];
  weakest: WeakestForm | null;
  /** Why no form is named, when none is, and how near the nearest one is. */
  weakest_gate: Gate;
  caveat: string | null;
}

export function getProgress(
  params: { period?: string; days?: number } = {},
): Promise<Progress> {
  return request<Progress>(`/progress${queryString(params)}`);
}

export function getRecommendations(
  params: { days?: number } = {},
): Promise<Recommendations> {
  return request<Recommendations>(`/progress/recommendations${queryString(params)}`);
}

/** Recompute this account's snapshots. Idempotent, and cheap when nothing changed. */
export function refreshProgress(
  params: { period?: string; days?: number } = {},
): Promise<Progress> {
  return request<Progress>(`/progress/refresh${queryString(params)}`, { method: "POST" });
}

/**
 * The points a chart can actually draw, in order.
 *
 * Shared by the chart and its tests because "which points are real" is the question the
 * whole component is built around, and a second implementation of it in the test would
 * assert against itself.
 */
export function drawablePoints(series: TrendSeries): TrendPoint[] {
  return series.points.filter((point) => point.value !== null);
}
