"""Read-aloud wire shapes: what `pron` returns, and what an attempt looks like.

Two families in one module because they are two views of the same numbers, and keeping
them apart in separate files would hide the one thing worth noticing: **the service
returns more per phone than the database stores.** `frames`, `gop_all_tokens` and
`r_composite` are diagnostics — they explain a score without re-running a model — and
they are dropped on the way to `phoneme_scores`. That is deliberate. A column exists
because something queries it across rows; a diagnostic exists because somebody is looking
at one attempt, and 250 extra values per reading that nothing aggregates is a table that
gets slower every week for no reader.

The one that is *not* dropped is `recognized_phone`, and it is the whole reason this
feature is worth building: "your /θ/ is weak" is a grade, and "you are producing /s/ where
English wants /θ/" is an instruction. On the probe set the model named the produced
phone correctly in 10 cases out of 10 — including the one case the threshold missed.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from models.audio import SourceMedia
from models.common import ORMModel, Slug

# ── What the pron service returns ───────────────────────────────────────────


class PhoneScore(BaseModel):
    """One scored phone, as `infra/pron/gop.py` emits it.

    Field names are the `phoneme_scores` column names on purpose: the API stores these
    without reshaping, and a wire format that had to be translated into a row would be a
    second place for the two to disagree.
    """

    word: str
    word_idx: int = Field(ge=0)
    phone_idx: int = Field(ge=0)
    canonical_phone: str

    # Nullable, and the nullability is the point: if the aligner reports a segment with
    # no phone that won it, the honest answer is "nothing", not a guess.
    recognized_phone: str | None = None

    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)

    # GOP is a log-posterior difference and is <= 0 by construction. `le=0` is not
    # decoration: a positive GOP would mean the canonical phone beat the maximum that
    # includes it, which is arithmetically impossible, so it can only mean the two
    # services have diverged. Better a 502 than a stored impossibility.
    gop: float = Field(le=0.0)
    posterior: float | None = Field(default=None, ge=0.0, le=1.0)

    # Diagnostics, not stored. See the module docstring.
    frames: int = Field(default=0, ge=0)
    gop_all_tokens: float | None = None
    r_composite: bool = False


class PronSummary(BaseModel):
    """The per-attempt aggregates, computed once by the service.

    `percentile_5` is the GOP below which 5 % of *this reading's* phones fall, so it
    carries a stated false-positive rate rather than being a constant somebody wrote
    down. It is reported per attempt and used as a threshold nowhere: calibrating a
    pass mark needs recordings from more than one speaker.
    """

    phones: int = Field(ge=0)
    mean_gop: float | None = None
    median_gop: float | None = None
    percentile_5: float | None = None
    r_composites: int = 0
    blank_dominated: int = 0


class PronScoring(BaseModel):
    """The whole `POST /score` response."""

    phones: list[PhoneScore]
    summary: PronSummary
    words: int = Field(ge=0)
    source: SourceMedia
    model: str
    latency_ms: int = Field(ge=0)


# ── What the API returns ────────────────────────────────────────────────────


class AttemptCreate(BaseModel):
    """Everything `POST /attempts` needs besides the recording itself.

    `session_id` is optional, and its absence is the ordinary case. A read-aloud session
    is bookkeeping — it is what groups several readings into one sitting — and requiring
    the client to create one first would put a round trip in front of the button. Omit it
    and the API opens one; pass it and the attempt joins that sitting.
    """

    passage_slug: Slug
    session_id: int | None = None


class PhonemeScoreOut(ORMModel):
    """One stored phone score, as the heatmap reads it."""

    word: str
    word_idx: int
    phone_idx: int
    canonical_phone: str
    recognized_phone: str | None
    start_ms: int | None
    end_ms: int | None
    gop: float
    posterior: float | None


class AttemptOut(ORMModel):
    """An attempt without its phones — the list view, and the poll response.

    `status` is the lifecycle the client polls on: `pending` → `scoring` → `scored` or
    `failed`. `error_message` is why a failure is a state rather than an absence: an
    attempt that failed must be able to say why and be retried.
    """

    id: int
    session_id: int
    passage_id: int
    passage_slug: str | None = None
    passage_title: str | None = None
    status: str
    transcript: str | None
    wer: float | None
    error_message: str | None
    scored_at: datetime | None
    created_at: datetime
    audio_url: str | None = None

    # How many phones were scored. On the list view this is the difference between "this
    # reading was scored" and "this reading was scored and there is something to look at",
    # and it saves the browser fetching every attempt's phones to render a history.
    phoneme_count: int = 0

    @classmethod
    def of(
        cls, attempt, *, passage=None, phoneme_count: int | None = None
    ) -> "AttemptOut":
        out = cls.model_validate(attempt)
        if attempt.audio_asset_id is not None:
            out.audio_url = f"/audio/{attempt.audio_asset_id}"
        if passage is not None:
            out.passage_slug = passage.slug
            out.passage_title = passage.title
        if phoneme_count is not None:
            out.phoneme_count = phoneme_count
        return out


class AttemptDetail(AttemptOut):
    """One attempt with everything: the passage text, the phones, the aggregates.

    The passage body is included rather than left for a second request. The heatmap tints
    words in place, so it needs the text and the scores at the same moment, and a screen
    that renders correctly only once two requests have both landed is a screen with a
    flash of wrong content in it.
    """

    passage_body: str | None = None
    phonemes: list[PhonemeScoreOut] = []

    # Present when the phones were scored, absent when `pron` was down. Recomputed from
    # the stored rows rather than stored: it is four numbers over 250 rows, and a stored
    # aggregate is a number that stops matching its inputs the day one of them changes.
    summary: PronSummary | None = None

    # ok | unavailable | rejected | protocol | misconfigured
    #
    # Separate from `status`, because "the reading was processed and the pronunciation
    # scorer was switched off" is a different fact from "the reading failed". An attempt
    # with `pron` down still returns its transcript and WER, and says so.
    pronunciation: str = "ok"
    pronunciation_detail: str | None = None


class AttemptPage(BaseModel):
    """`GET /attempts` — newest first, bounded server-side like `GET /sessions`."""

    items: list[AttemptOut]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
