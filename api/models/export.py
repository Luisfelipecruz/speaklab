"""One account's whole history, as a single document a person can keep.

**Everything the account made.** Sessions with their turns, each turn with the
measurements and corrections taken from it, every reading with its scored sounds, every
spoken answer, and the weekly snapshots the progress page reads. Scenarios, passages and
prompts are named by slug rather than copied: they are catalogue content, the same for
every account, and not part of anybody's history.

**Recordings are addresses, not bytes.** Each is listed with its length, format and hash,
and with the `/audio/{id}` path that streams it to its owner. A JSON document is no place
for megabytes of base64, and that path is ownership-checked like everything else.

**Left out on purpose:** the password hash, which is a credential rather than a record,
and what the system keeps to run a conversation rather than to describe one — the summary
a long conversation is condensed into for the model, the token counts, and the analyser's
refused proposals.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from models.common import ORMModel


class ExportAccount(ORMModel):
    id: int
    email: str
    native_language: str
    cefr_self_assessed: str | None
    retain_audio: bool
    created_at: datetime


class ExportRecording(ORMModel):
    """One stored recording, and where its owner can fetch it."""

    id: int
    url: str = ""
    duration_ms: int
    sample_rate: int
    format: str
    sha256: str
    device_hint: str | None
    created_at: datetime

    @classmethod
    def of(cls, asset) -> "ExportRecording":
        out = cls.model_validate(asset)
        out.url = f"/audio/{asset.id}"
        return out


class ExportFluency(ORMModel):
    word_count: int | None
    speech_rate_wpm: float | None
    articulation_rate: float | None
    pause_ratio: float | None
    mean_length_run: float | None
    filler_count: int | None
    response_latency_ms: int | None


class ExportCorrection(ORMModel):
    category: str
    subcategory: str | None
    span_start: int | None
    span_end: int | None
    original: str
    correction: str
    explanation: str | None
    form: str | None
    corrected_form: str | None
    detector: str
    confidence: float
    asr_suspect: bool


class ExportTurn(ORMModel):
    """One turn, with what was measured and corrected in it underneath."""

    idx: int
    role: str
    transcript: str | None
    words: list[dict] | None
    asr_confidence: float | None
    asr_model: str | None
    llm_model: str | None
    tts_voice: str | None
    latency_ms: int | None
    created_at: datetime
    audio_url: str | None = None
    analysis_status: str | None
    analyzed_at: datetime | None

    # Null on an assistant turn and on a user turn not analysed yet.
    fluency: ExportFluency | None = None
    # Verb forms counted in the turn, by form.
    forms: dict[str, int] = Field(default_factory=dict)
    corrections: list[ExportCorrection] = Field(default_factory=list)


class ExportSession(BaseModel):
    id: int
    scenario_slug: str | None
    mode: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    report: dict | None
    turns: list[ExportTurn] = Field(default_factory=list)


class ExportPhone(ORMModel):
    word: str
    word_idx: int
    phone_idx: int
    canonical_phone: str
    recognized_phone: str | None
    start_ms: int | None
    end_ms: int | None
    gop: float
    posterior: float | None


class ExportReading(ORMModel):
    """One read-aloud attempt, with every sound that was scored in it."""

    id: int
    session_id: int
    passage_slug: str | None = None
    status: str
    transcript: str | None
    wer: float | None
    error_message: str | None
    scored_at: datetime | None
    created_at: datetime
    audio_url: str | None = None
    phones: list[ExportPhone] = Field(default_factory=list)


class ExportAnswer(ORMModel):
    id: int
    prompt_slug: str | None = None
    again_of: int | None
    transcript: str
    words: list[dict]
    duration_ms: int | None
    asr_confidence: float | None
    asr_model: str | None
    delivery: dict
    structure: dict
    feedback: dict | None
    created_at: datetime


class ExportSnapshot(ORMModel):
    period: str
    period_start: date
    fluency: dict
    accuracy: dict
    complexity: dict
    pronunciation: dict
    sample_counts: dict
    updated_at: datetime


class HistoryExport(BaseModel):
    """The document `GET /progress/export` sends."""

    exported_at: datetime
    # The API version that wrote the document, so a reader knows which shape it has.
    version: str
    account: ExportAccount
    recordings: list[ExportRecording] = Field(default_factory=list)
    sessions: list[ExportSession] = Field(default_factory=list)
    readings: list[ExportReading] = Field(default_factory=list)
    answers: list[ExportAnswer] = Field(default_factory=list)
    snapshots: list[ExportSnapshot] = Field(default_factory=list)
