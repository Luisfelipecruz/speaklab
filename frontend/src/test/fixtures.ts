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
  CategoryCorrections,
  CorrectionExample,
  Drill,
  DrillResult,
  FormPractice,
  GrammarPage,
  MetricFamily,
  PassageDetail,
  PhonemeScore,
  Progress,
  Recommendations,
  Repertoire,
  ScenarioSummary,
  SessionAnalysis,
  SessionDetail,
  SessionReportShape,
  TrendSeries,
  Turn,
} from "@/lib/api";
import type { UserProfile } from "@/lib/auth";

/** A signed-in account, for anything that renders around the session. */
export function makeProfile(overrides: Partial<UserProfile> = {}): UserProfile {
  return {
    id: 1,
    email: "someone@example.com",
    native_language: "es",
    cefr_self_assessed: "B1",
    retain_audio: true,
    created_at: "2026-08-30T10:00:00Z",
    ...overrides,
  };
}


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

// ── Progress ────────────────────────────────────────────────────────────────

/**
 * A series with three measured weeks in it.
 *
 * The default is a *drawable* series, because most tests are about what happens around
 * one — a suppressed gate, a hole, a direction — and each of those is one override rather
 * than a whole object rebuilt by hand.
 */
export function makeSeries(overrides: Partial<TrendSeries> = {}): TrendSeries {
  return {
    metric: "errors_per_100_words",
    label: "errors",
    unit: "per 100 words",
    better: "lower",
    points: [
      { start: "2026-08-17", value: 8, samples: 210, withheld: null },
      { start: "2026-08-24", value: 6, samples: 240, withheld: null },
      { start: "2026-08-31", value: 3, samples: 300, withheld: null },
    ],
    gate: { shown: true, reason: null, have: 3, need: 1 },
    change: -5,
    direction: "improving",
    ...overrides,
  };
}

export function makeFamily(overrides: Partial<MetricFamily> = {}): MetricFamily {
  return {
    name: "accuracy",
    label: "What you get wrong",
    description: "Counted from stored corrections, per hundred words.",
    series: [makeSeries()],
    caveat: null,
    ...overrides,
  };
}

export function makeRepertoire(overrides: Partial<Repertoire> = {}): Repertoire {
  return {
    latest_period: "2026-08-31",
    forms: { present_simple: 9, past_simple: 4, going_to_future: 1 },
    distinct_forms: 3,
    previous_distinct_forms: 3,
    accuracy: {},
    accuracy_floor: 10,
    caveat: null,
    warning: null,
    ...overrides,
  };
}

export function makeProgress(overrides: Partial<Progress> = {}): Progress {
  return {
    period: "week",
    since: "2026-08-03",
    until: "2026-09-05",
    totals: {
      sessions: 2,
      turns: 7,
      words: 272,
      attempts: 2,
      phones: 450,
      periods: 1,
    },
    families: [makeFamily()],
    phones: [],
    phone_gate: {
      shown: false,
      reason:
        "2 scored readings so far. Per-sound trends start at 5, because the first few readings describe your microphone as much as your mouth.",
      have: 2,
      need: 5,
    },
    repertoire: makeRepertoire(),
    stale: false,
    ...overrides,
  };
}

export function makeRecommendations(
  overrides: Partial<Recommendations> = {},
): Recommendations {
  return {
    items: [
      {
        kind: "error_category",
        title: "verb tense",
        reason: "6 corrections in 272 words — 2.2 per 100 words, your most frequent category.",
        measured: 2.2,
        samples: 6,
        score: 0.98,
        scenario_slug: null,
        passage_slug: null,
      },
      {
        kind: "weak_phone",
        title: "the /TH/ sound",
        reason: "30 instances scored, -1.8 standard deviations from your own recent readings of it.",
        measured: -1.8,
        samples: 30,
        score: 0.81,
        scenario_slug: null,
        passage_slug: "third-street-theatre",
      },
      {
        kind: "unused_form",
        title: "conditional 2",
        reason: "Not once in 272 words of practice.",
        measured: 0,
        samples: 272,
        score: 0.72,
        scenario_slug: "job-interview-backend",
        passage_slug: null,
      },
    ],
    confidence: "low",
    detail:
      "Based on 272 words and 2 scored readings. That is enough to notice a pattern and not enough to be sure of one — practise a few more times and these will change.",
    ...overrides,
  };
}

// ── Grammar ─────────────────────────────────────────────────────────────────

export function makeCorrectionExample(
  overrides: Partial<CorrectionExample> = {},
): CorrectionExample {
  return {
    id: 41,
    session_id: 12,
    turn_id: 6,
    said_at: "2026-08-30T10:04:00Z",
    scenario_title: "Daily standup",
    before: "Yesterday ",
    quote: "I complete the user story",
    after: " and we request a review.",
    original: "I complete the user story",
    correction: "I completed the user story",
    explanation: "Yesterday needs the past simple.",
    subcategory: "missing_past_marker",
    detector: "llm",
    counted: true,
    asr_suspect: false,
    form: "present_simple",
    corrected_form: "past_simple",
    ...overrides,
  };
}

export function makeCategory(overrides: Partial<CategoryCorrections> = {}): CategoryCorrections {
  return {
    category: "VERB_TENSE",
    label: "verb tense",
    description: "the form of a verb is wrong: went/gone, is working/works",
    counted: 1,
    not_counted: 0,
    per_100_words: 0.37,
    by_detector: { llm: 1 },
    examples: [makeCorrectionExample()],
    ...overrides,
  };
}

export function makeFormPractice(overrides: Partial<FormPractice> = {}): FormPractice {
  return {
    form: "present_simple",
    label: "present simple",
    used: 12,
    right: 11,
    wrong: 1,
    missed: 0,
    corrections: [
      {
        id: 41,
        session_id: 12,
        original: "I complete the user story",
        correction: "I completed the user story",
        form: "present_simple",
        corrected_form: "past_simple",
      },
    ],
    ...overrides,
  };
}

export function makeGrammarPage(overrides: Partial<GrammarPage> = {}): GrammarPage {
  return {
    since: "2026-08-12",
    until: "2026-09-11",
    totals: { sessions: 2, turns: 7, words: 272, corrections: 1, counted: 1 },
    categories: [makeCategory()],
    forms: [
      makeFormPractice(),
      makeFormPractice({
        form: "past_simple",
        label: "past simple",
        used: 0,
        right: 0,
        wrong: 0,
        missed: 1,
      }),
    ],
    weakest: null,
    weakest_gate: {
      shown: false,
      reason:
        "The form with the most corrections so far is the present simple: 1 correction, from the 12 times it was said or needed. A form is named here once it has come up 10 times and been corrected 5 times.",
      have: 1,
      need: 5,
    },
    caveat: "Every correction here was proposed by grammar rules or by a language model.",
    ...overrides,
  };
}

export function makeDrill(overrides: Partial<Drill> = {}): Drill {
  return {
    id: 41,
    session_id: 12,
    turn_id: 6,
    said_at: "2026-08-30T10:04:00Z",
    scenario_title: "Daily standup",
    corrections: [
      {
        id: 41,
        category: "VERB_TENSE",
        label: "verb tense",
        subcategory: "missing_past_marker",
        original: "I complete",
        correction: "I completed",
        explanation: "Yesterday needs the past simple.",
        detector: "llm",
        counted: true,
        asr_suspect: false,
      },
    ],
    pieces: [
      { said: "Yesterday ", say: "Yesterday ", correction_id: null },
      { said: "I complete", say: "I completed", correction_id: 41 },
      { said: " the user story.", say: " the user story.", correction_id: null },
    ],
    unavailable: null,
    cut_before: false,
    cut_after: false,
    next_id: 44,
    caveat: "The recogniser was trained on fluent English, and it can hear the correct form.",
    ...overrides,
  };
}

export function makeDrillResult(overrides: Partial<DrillResult> = {}): DrillResult {
  return {
    heard: "Yesterday I completed the user story.",
    words: ["yesterday", "i", "completed", "the", "user", "story"].map((word) => ({
      expected: word,
      heard: word,
    })),
    verdicts: [
      { id: 41, verdict: "corrected", expected: "i completed", heard: "i completed", unsure: false },
    ],
    expected_words: 6,
    matched: 6,
    substituted: 0,
    missed: 0,
    added: 0,
    ...overrides,
  };
}
