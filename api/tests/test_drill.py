"""Say it again: the sentence, the comparison, and the two operations.

**The comparison is tested against known transcripts, with no audio.** Every case is a
sentence to say and a transcript of what was heard, and the assertion is what the drill
says about each correction in it. That is where the drill's claims live — which words
stood where the correction belongs — and none of it needs a recogniser to be running. What
the recogniser does to a learner's error on the way is a measurement, and it is in the
speech recognition suite.

The endpoints are tested with the recogniser replaced, on rows inserted directly as the
grammar page's tests insert them.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from db_models import AudioAsset, LanguageError, Turn
from models.audio import DecoderSettings, SourceMedia, Transcription, Word
from models.drill import DrillPiece
from services import drill
from tests.test_corrections import fix, practise


def heard(text: str, unsure: tuple[str, ...] = ()) -> Transcription:
    """A transcript as the recogniser returns it; words named in `unsure` at probability 0.3."""
    words = [
        Word(
            w=(" " if index else "") + token,
            start_ms=index * 300,
            end_ms=index * 300 + 250,
            logprob=-1.2 if token.strip(".,?!").lower() in unsure else -0.05,
        )
        for index, token in enumerate(text.split())
    ]
    return Transcription(
        text=text,
        words=words,
        confidence=0.9,
        timestamp_fixups=0,
        language="en",
        model="stub-whisper",
        decoder=DecoderSettings(beam_size=5, vad_filter=True, compute_type="int8"),
        source=SourceMedia(
            format="wav",
            codec="pcm_s16le",
            sample_rate=16000,
            channels=1,
            duration_ms=900,
        ),
        latency_ms=5,
    )


def said(transcript: str, *changes: tuple[str, str]) -> list[DrillPiece]:
    """The whole transcript as a drill, with each `(quote, correction)` applied."""
    rows = []
    for number, (quote, correction) in enumerate(changes, start=1):
        start = transcript.index(quote)
        rows.append(
            SimpleNamespace(
                id=number,
                span_start=start,
                span_end=start + len(quote),
                original=quote,
                correction=correction,
            )
        )
    rows.sort(key=lambda row: row.span_start)
    return drill.pieces(transcript, rows, 0, len(transcript))


YESTERDAY = said("Yesterday she say the plan was good.", ("she say", "she said"))


def verdict(sentence, text, **kwargs):
    return [
        (v.verdict, v.heard)
        for v in drill.score(sentence, heard(text, **kwargs)).verdicts
    ]


# ── The sentence ────────────────────────────────────────────────────────────


def test_the_sentence_is_the_one_said_with_the_correction_in_it():
    assert (
        "".join(piece.said for piece in YESTERDAY)
        == "Yesterday she say the plan was good."
    )
    assert (
        "".join(piece.say for piece in YESTERDAY)
        == "Yesterday she said the plan was good."
    )
    assert [piece.correction_id for piece in YESTERDAY] == [None, 1, None]


def test_every_correction_in_the_sentence_is_applied():
    sentence = said(
        "Yesterday I go to the office and she say it was fine.",
        ("I go", "I went"),
        ("she say", "she said"),
    )
    assert (
        "".join(p.say for p in sentence)
        == "Yesterday I went to the office and she said it was fine."
    )


def test_the_correction_practised_wins_an_overlap_and_the_rest_go_by_position():
    transcript = "Yesterday I go to the office early."
    practised = SimpleNamespace(
        id=2, span_start=12, span_end=14, original="go", correction="went"
    )
    overlapping = SimpleNamespace(
        id=1, span_start=10, span_end=14, original="I go", correction="I have gone"
    )
    later = SimpleNamespace(
        id=3, span_start=18, span_end=28, original="the office", correction="work"
    )

    chosen = drill.applied(
        transcript, practised, [overlapping, later, practised], 0, 35
    )

    assert [row.id for row in chosen] == [2, 3]


def test_a_correction_outside_the_sentence_or_off_its_words_is_left_alone():
    transcript = "I go home. She say hello."
    practised = SimpleNamespace(
        id=1, span_start=2, span_end=4, original="go", correction="went"
    )
    next_sentence = SimpleNamespace(
        id=2, span_start=11, span_end=18, original="She say", correction="She said"
    )
    misplaced = SimpleNamespace(
        id=3, span_start=5, span_end=9, original="house", correction="the house"
    )

    assert drill.applied(transcript, practised, [next_sentence, misplaced], 0, 10) == [
        practised
    ]


def test_a_change_of_capitals_or_punctuation_is_not_something_to_say():
    assert not drill.audible(SimpleNamespace(original="i think", correction="I think,"))
    assert drill.audible(SimpleNamespace(original="she say", correction="she says"))


# ── The comparison ──────────────────────────────────────────────────────────


def test_the_corrected_words_heard_in_their_place():
    result = drill.score(YESTERDAY, heard("Yesterday she said the plan was good."))

    (only,) = result.verdicts
    assert (only.verdict, only.expected, only.heard) == (
        "corrected",
        "she said",
        "she said",
    )
    assert (result.expected_words, result.matched) == (7, 7)
    assert result.substituted == result.missed == result.added == 0


def test_the_words_as_first_said_are_named_as_that():
    assert verdict(YESTERDAY, "yesterday she say the plan was good") == [
        ("original", "she say")
    ]


def test_something_else_in_their_place_is_neither():
    assert verdict(YESTERDAY, "Yesterday she sad the plan was good.") == [
        ("other", "she sad")
    ]


def test_nothing_heard_where_the_correction_belongs():
    result = drill.score(YESTERDAY, heard("Yesterday the plan was good."))

    assert [(v.verdict, v.heard) for v in result.verdicts] == [("unheard", "")]
    assert result.missed == 2


def test_capitals_and_punctuation_are_not_heard_and_not_counted():
    assert verdict(YESTERDAY, "YESTERDAY, she said: the plan was good!") == [
        ("corrected", "she said")
    ]


def test_a_missing_article_said_without_it_is_the_original():
    sentence = said("My sister is teacher in Seville.", ("is teacher", "is a teacher"))

    assert verdict(sentence, "My sister is teacher in Seville.") == [
        ("original", "is teacher")
    ]
    assert verdict(sentence, "My sister is a teacher in Seville.") == [
        ("corrected", "is a teacher")
    ]


def test_a_word_the_correction_removes_is_heard_as_the_original_when_it_is_said():
    sentence = said("I am agree with you.", ("am agree", "agree"))

    assert verdict(sentence, "I am agree with you.") == [("original", "am agree")]
    assert verdict(sentence, "I agree with you.") == [("corrected", "agree")]


def test_a_correction_that_only_removes_words_is_heard_between_its_neighbours():
    sentence = said("We discussed about the plan.", (" about", ""))

    assert verdict(sentence, "We discussed the plan.") == [("corrected", "")]
    assert verdict(sentence, "We discussed about the plan.") == [("original", "about")]
    assert verdict(sentence, "We discussed over the plan.") == [("other", "over")]


def test_each_correction_in_the_sentence_gets_its_own_verdict():
    sentence = said(
        "Yesterday I go to the office and she say it was fine.",
        ("I go", "I went"),
        ("she say", "she said"),
    )

    assert verdict(
        sentence, "Yesterday I went to the office and she say it was fine."
    ) == [
        ("corrected", "i went"),
        ("original", "she say"),
    ]


def test_a_word_the_recogniser_was_unsure_of_marks_the_verdict():
    (unsure,) = drill.score(
        YESTERDAY, heard("Yesterday she said the plan was good.", unsure=("said",))
    ).verdicts
    (sure,) = drill.score(
        YESTERDAY, heard("Yesterday she said the plan was good.", unsure=("plan",))
    ).verdicts

    assert unsure.unsure is True
    assert sure.unsure is False


def test_the_sentence_is_counted_word_by_word():
    result = drill.score(YESTERDAY, heard("Yesterday she said a plan was very good."))

    assert (result.matched, result.substituted, result.missed, result.added) == (
        6,
        1,
        0,
        1,
    )
    assert [(w.expected, w.heard) for w in result.words] == [
        ("yesterday", "yesterday"),
        ("she", "she"),
        ("said", "said"),
        ("the", "a"),
        ("plan", "plan"),
        ("was", "was"),
        (None, "very"),
        ("good", "good"),
    ]


def test_words_that_cannot_be_matched_to_the_transcript_carry_no_doubt():
    transcription = heard("Yesterday she said the plan was good.", unsure=("said",))
    transcription.words = transcription.words[:3]

    (only,) = drill.score(YESTERDAY, transcription).verdicts

    assert only.verdict == "corrected" and only.unsure is False


def test_silence_is_every_word_missed():
    result = drill.score(YESTERDAY, heard(""))

    assert result.missed == 7 and result.matched == 0
    assert [v.verdict for v in result.verdicts] == ["unheard"]


# ── The operations ──────────────────────────────────────────────────────────

STANDUP = (
    "Good morning. Yesterday I go to the office and she say the plan was good. "
    "Then I finish early."
)
GO = fix("I go", "I went", form="present_simple", corrected_form="past_simple")
SAY = fix(
    "she say",
    "she said",
    "SUBJECT_VERB_AGREEMENT",
    form="present_simple",
    corrected_form="past_simple",
    detector="rule",
    confidence=1.0,
)
FINISH = fix(
    "I finish", "I finished", form="present_simple", corrected_form="past_simple"
)


async def ids(db, turn) -> dict[str, int]:
    rows = (
        await db.execute(
            select(LanguageError.original, LanguageError.id).where(
                LanguageError.turn_id == turn.id
            )
        )
    ).all()
    return dict(rows)


async def test_the_drill_needs_an_account(client):
    assert (await client.get("/corrections/1/drill")).status_code == 401


@pytest.mark.usefixtures("seeded")
async def test_the_sentence_comes_back_with_every_correction_in_it(
    client, account, db_session
):
    turn = await practise(db_session, account["id"], STANDUP, [GO, SAY, FINISH])
    found = await ids(db_session, turn)

    body = (await client.get(f"/corrections/{found['I go']}/drill")).json()

    assert body["unavailable"] is None
    assert "".join(p["said"] for p in body["pieces"]) == (
        "Yesterday I go to the office and she say the plan was good."
    )
    assert "".join(p["say"] for p in body["pieces"]) == (
        "Yesterday I went to the office and she said the plan was good."
    )
    assert [c["original"] for c in body["corrections"]] == ["I go", "she say"]
    assert body["corrections"][1]["detector"] == "rule"
    assert body["corrections"][0]["label"] == "verb tense"
    assert body["scenario_title"] == "Daily standup"
    assert body["session_id"] == turn.session_id
    # The same kind, and not already in this sentence.
    assert body["next_id"] == found["I finish"]
    assert "rather than proof you said it" in body["caveat"]


@pytest.mark.usefixtures("seeded")
async def test_the_next_correction_is_the_next_of_its_kind_newest_first(
    client, account, db_session
):
    older = await practise(
        db_session,
        account["id"],
        "Last week I visit my aunt.",
        [fix("I visit", "I visited")],
        days_ago=3,
    )
    newer = await practise(db_session, account["id"], STANDUP, [GO, SAY, FINISH])
    first, last = await ids(db_session, newer), await ids(db_session, older)

    after_go = (await client.get(f"/corrections/{first['I go']}/drill")).json()
    after_finish = (await client.get(f"/corrections/{first['I finish']}/drill")).json()
    after_visit = (await client.get(f"/corrections/{last['I visit']}/drill")).json()

    assert after_go["next_id"] == first["I finish"]
    assert after_finish["next_id"] == last["I visit"]
    assert after_visit["next_id"] is None


@pytest.mark.usefixtures("seeded")
async def test_a_correction_off_its_words_is_shown_and_not_offered(
    client, account, db_session, recogniser
):
    turn = await practise(db_session, account["id"], STANDUP, [GO])
    row = await db_session.scalar(
        select(LanguageError).where(LanguageError.turn_id == turn.id)
    )
    row.original = "I goes"
    await db_session.commit()

    body = (await client.get(f"/corrections/{row.id}/drill")).json()
    said_it = await client.post(
        f"/corrections/{row.id}/drill", files={"file": ("a.wav", b"RIFF", "audio/wav")}
    )

    assert body["pieces"] == [] and "not where it says" in body["unavailable"]
    assert body["corrections"][0]["correction"] == "I went"
    assert said_it.status_code == 409


@pytest.mark.usefixtures("seeded")
async def test_a_change_only_of_capitals_is_not_offered(client, account, db_session):
    turn = await practise(
        db_session, account["id"], "i think so.", [fix("i think", "I think")]
    )
    (found,) = (await ids(db_session, turn)).values()

    body = (await client.get(f"/corrections/{found}/drill")).json()

    assert "only capitals or punctuation" in body["unavailable"]


@pytest.mark.usefixtures("seeded")
async def test_another_accounts_correction_is_not_found(
    client, account, other_client, db_session, recogniser
):
    from tests.conftest import register_account

    turn = await practise(db_session, account["id"], STANDUP, [GO])
    (found,) = (await ids(db_session, turn)).values()
    await register_account(other_client)
    recogniser.append("never heard")

    read = await other_client.get(f"/corrections/{found}/drill")
    said_it = await other_client.post(
        f"/corrections/{found}/drill", files={"file": ("a.wav", b"RIFF", "audio/wav")}
    )
    missing = await client.get("/corrections/999999999/drill")

    assert read.status_code == said_it.status_code == missing.status_code == 404
    assert recogniser == ["never heard"]


@pytest.mark.usefixtures("seeded")
async def test_saying_it_again_is_compared_and_nothing_is_kept(
    client, account, db_session, recogniser, audio_root
):
    turn = await practise(db_session, account["id"], STANDUP, [GO, SAY])
    found = await ids(db_session, turn)
    recogniser.append("Yesterday I went to the office and she say the plan was good.")

    async def stored() -> tuple[int, int]:
        return (
            await db_session.scalar(select(func.count()).select_from(Turn)),
            await db_session.scalar(select(func.count()).select_from(AudioAsset)),
        )

    before = await stored()

    response = await client.post(
        f"/corrections/{found['I go']}/drill",
        files={"file": ("again.webm", b"not really audio", "audio/webm")},
    )

    assert response.status_code == 200
    body = response.json()
    assert [(v["id"], v["verdict"]) for v in body["verdicts"]] == [
        (found["I go"], "corrected"),
        (found["she say"], "original"),
    ]
    assert body["heard"].startswith("Yesterday I went")
    assert (body["expected_words"], body["matched"], body["substituted"]) == (13, 12, 1)
    assert await stored() == before
    assert list(audio_root.iterdir()) == []


@pytest.mark.usefixtures("seeded")
async def test_a_recording_over_the_limit_is_refused_before_it_is_heard(
    client, account, db_session, recogniser, monkeypatch
):
    from routers import drills

    monkeypatch.setattr(drills, "MAX_UPLOAD_BYTES", 10)
    turn = await practise(db_session, account["id"], STANDUP, [GO])
    (found,) = (await ids(db_session, turn)).values()
    recogniser.append("never heard")

    response = await client.post(
        f"/corrections/{found}/drill", files={"file": ("a.wav", b"x" * 11, "audio/wav")}
    )

    assert response.status_code == 413
    assert recogniser == ["never heard"]


@pytest.mark.usefixtures("seeded")
async def test_a_recogniser_that_is_down_is_a_503_and_says_so(
    client, account, db_session, monkeypatch
):
    from routers import turns
    from services.asr_client import AsrUnavailable

    async def down(data, filename="recording", content_type=None):
        raise AsrUnavailable("refused")

    monkeypatch.setattr(turns, "transcribe", down)
    turn = await practise(db_session, account["id"], STANDUP, [GO])
    (found,) = (await ids(db_session, turn)).values()

    response = await client.post(
        f"/corrections/{found}/drill", files={"file": ("a.wav", b"RIFF", "audio/wav")}
    )

    assert response.status_code == 503
    assert "recogniser" in response.json()["detail"]
