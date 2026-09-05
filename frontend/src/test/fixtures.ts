/**
 * Shapes for tests, matching what the API actually returns.
 *
 * Test-only, and never imported by application code — the point of building a turn here
 * rather than in each test is that when `TurnOut` gains a field, one file stops
 * compiling instead of nine tests silently asserting against a shape the server no
 * longer sends.
 */

import type {
  AttemptDetail,
  PassageDetail,
  PhonemeScore,
  ScenarioSummary,
  SessionAnalysis,
  SessionDetail,
  SessionReportShape,
  Turn,
} from "@/lib/api";

export function makeTurn(overrides: Partial<Turn> = {}): Turn {
  return {
    id: 1,
    idx: 0,
    role: "assistant",
    transcript: "Good morning. Thanks for coming in — shall we start with your last role?",
    audio_asset_id: 7,
    audio_url: "/audio/7",
    asr_confidence: null,
    asr_model: null,
    llm_model: "gemma3:4b",
    tts_voice: "en_US-lessac-medium",
    latency_ms: 2353,
    created_at: "2026-08-30T10:00:00Z",
    low_confidence: false,
    ...overrides,
  };
}

export function makeSession(overrides: Partial<SessionDetail> = {}): SessionDetail {
  return {
    id: 12,
    scenario_slug: "job-interview-backend",
    scenario_title: "Job interview — backend engineer",
    mode: "conversation",
    status: "active",
    started_at: "2026-08-30T10:00:00Z",
    ended_at: null,
    turn_count: 1,
    turns: [makeTurn()],
    report: null,
    ...overrides,
  };
}

export function makeScenario(overrides: Partial<ScenarioSummary> = {}): ScenarioSummary {
  return {
    slug: "job-interview-backend",
    title: "Job interview — backend engineer",
    description: "A hiring manager who will push back on vague answers.",
    category: "workplace",
    cefr_band: "B2",
    target_grammar: ["present_perfect", "past_simple", "conditionals"],
    target_functions: ["describing_experience"],
    ...overrides,
  };
}

export function makeAnalysis(overrides: Partial<SessionAnalysis> = {}): SessionAnalysis {
  return {
    complete: true,
    turns_analysed: 6,
    turns_outstanding: 0,
    fluency: {
      words_spoken: 318,
      speech_rate_wpm: 118.4,
      articulation_rate_wpm: 141.2,
      pause_ratio: 0.16,
      mean_length_run: 9.3,
      filler_count: 2,
      fillers_per_100_words: 0.63,
      mean_pause_before_speaking_ms: 640,
    },
    grammar_usage: { past_simple: 7, present_perfect: 2, main_clause: 11 },
    target_forms: {
      declared: ["present_perfect", "past_simple", "conditional_2"],
      elicited: ["present_perfect", "past_simple"],
      not_elicited: ["conditional_2"],
    },
    errors: {
      total: 2,
      counted: 1,
      asr_suspect: 1,
      low_confidence: 0,
      per_100_words: 0.31,
      by_category: { VERB_TENSE: 1 },
      items: [
        {
          turn_id: 6,
          category: "VERB_TENSE",
          subcategory: "missing_past_marker",
          span_start: 10,
          span_end: 28,
          original: "I complete the user story",
          correction: "I completed the user story",
          explanation: "Yesterday needs the past simple.",
          confidence: 0.9,
          asr_suspect: false,
          counted: true,
        },
        {
          turn_id: 8,
          category: "PREPOSITION",
          subcategory: "wrong",
          span_start: 4,
          span_end: 20,
          original: "look department",
          correction: "look at the apartment",
          explanation: "This may be a mishearing.",
          confidence: 0.7,
          asr_suspect: true,
          counted: false,
        },
      ],
      rejected: 1,
      rejection_rate: 0.3333,
      rejected_reasons: { unknown_category: 1 },
    },
    ...overrides,
  };
}

export function makeReport(overrides: Partial<SessionReportShape> = {}): SessionReportShape {
  return {
    schema: 2,
    scenario: "job-interview-backend",
    goal: "Explain a project you led and answer two challenges to your timeline.",
    measured: {
      turns: { total: 12, user: 6, assistant: 6 },
      duration_ms: 245_000,
      words_spoken: 318,
      mean_asr_confidence: 0.87,
      median_turn_latency_ms: 2353,
      reached_min_turns: true,
      min_turns: 6,
    },
    narrative: {
      status: "ok",
      by: "llm",
      model: "gemma3:4b",
      summary: "You described a migration project and defended the schedule twice.",
      goal_met: true,
      note: "You gave concrete numbers when challenged, which is what made it convincing.",
    },
    analysis: makeAnalysis(),
    pending: {
      pronunciation: "Per-phoneme GOP, which read-aloud practice produces",
    },
    ...overrides,
  };
}

// ── Read-aloud ──────────────────────────────────────────────────────────────

export function makePassage(overrides: Partial<PassageDetail> = {}): PassageDetail {
  return {
    slug: "third-street-theatre",
    title: "The Third Street theatre",
    cefr_band: "B1",
    phoneme_focus: ["TH"],
    word_count: 79,
    body: "The theatre on Third Street is worth the trip. I thanked the usher.",
    ...overrides,
  };
}

export function makePhoneme(overrides: Partial<PhonemeScore> = {}): PhonemeScore {
  return {
    word: "the",
    word_idx: 0,
    phone_idx: 0,
    canonical_phone: "DH",
    recognized_phone: "ð",
    start_ms: 0,
    end_ms: 60,
    gop: 0,
    posterior: 0.91,
    ...overrides,
  };
}

export function makeAttempt(overrides: Partial<AttemptDetail> = {}): AttemptDetail {
  return {
    id: 5,
    session_id: 12,
    passage_id: 1,
    passage_slug: "third-street-theatre",
    passage_title: "The Third Street theatre",
    status: "scored",
    transcript: "the theatre on third street is worth the trip i sanked the usher",
    wer: 0.08,
    error_message: null,
    scored_at: "2026-08-30T10:00:12Z",
    created_at: "2026-08-30T10:00:00Z",
    audio_url: "/audio/9",
    phoneme_count: 2,
    passage_body: "The theatre on Third Street is worth the trip. I thanked the usher.",
    phonemes: [],
    summary: null,
    pronunciation: "ok",
    pronunciation_detail: null,
    ...overrides,
  };
}
