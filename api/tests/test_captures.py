"""Say it in English and the Notebook, through the routes, with the recogniser and the
language model replaced.

What is asserted is what the feature promises: the English goes back in one model call
and the rest follows; nothing is kept while saving is paused, and never the recording;
English the person wrote is counted as writing and English they said is not; a written
mistake never moves a spoken figure; deleting takes everything written with it; and
nobody reaches another account's captures.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from config import ASR_MULTI_URL
from db_models import AudioAsset, Capture, CaptureAttempt, CapturePhrase, WrittenError
from main import app
from models.audio import DecoderSettings, SourceMedia, Transcription, Word
from services import captures as notebook
from services.wer import normalise
from services.asr_client import AsrUnavailable
from services.llm import get_provider
from tests.conftest import register_account
from tests.say_provider import DIRECT, ORGANIZED, POLISHED, SayProvider

SPANISH = (
    "Laura, te escribo para avisarte que el informe del cliente se va a retrasar hasta el "
    "jueves 14, porque todavía estamos esperando los datos de Acme."
)
ENGLISH_TYPED = "I recieved your message and I will call you tomorow."
ENGLISH_SAID = "I received your message and I will call you tomorrow"
ROUGH = "Laura, I write you to let you know the customer's report is delayed to Thursday 14."


@pytest.fixture
def model():
    stub = SayProvider()
    app.dependency_overrides[get_provider] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_provider, None)


@pytest_asyncio.fixture(autouse=True)
async def writer(db_engine, model):
    """The work behind the reply, run when the test says, on the test database."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    class RecordingWriter(notebook.Writer):
        def __init__(self):
            super().__init__(factory, model)
            self.launched: list[int] = []

        def launch(self, capture_id: int) -> None:
            self.launched.append(capture_id)

        async def drain(self) -> None:
            queued, self.launched = self.launched, []
            for capture_id in queued:
                await notebook.write_rest(capture_id, factory, model)

    stub = RecordingWriter()
    app.dependency_overrides[notebook.get_writer] = lambda: stub
    yield stub
    app.dependency_overrides.pop(notebook.get_writer, None)


@pytest.fixture
def hearing(monkeypatch):
    """The recogniser for the account's own language. Queue (text, language) pairs."""

    class Hearing:
        def __init__(self):
            self.queue: list[tuple[str, str]] = []
            self.calls: list[dict] = []
            self.error: Exception | None = None
            # How sure it was of each transcript, when it heard the recording both ways.
            self.confidences: dict[str, float] | None = None

        async def __call__(
            self,
            data,
            filename="recording",
            content_type=None,
            client=None,
            language=None,
            task=None,
            url=None,
        ):
            self.calls.append({"language": language, "task": task, "url": url})
            if self.error is not None:
                raise self.error
            text, heard_in = self.queue.pop(0) if self.queue else (SPANISH, "es")
            if task == "translate":
                text, heard_in = ROUGH, "en"
            words = [
                Word(w=w, start_ms=i * 300, end_ms=i * 300 + 250, logprob=-0.1)
                for i, w in enumerate(text.split())
            ]
            return Transcription(
                text=text,
                words=words,
                confidence=0.93,
                timestamp_fixups=0,
                language=heard_in,
                task=task or "transcribe",
                language_scores=(
                    {heard_in: 0.97} if language and "," in language else None
                ),
                language_confidences=(
                    self.confidences if language and "," in language else None
                ),
                model="stub-small",
                decoder=DecoderSettings(
                    beam_size=5, vad_filter=True, compute_type="int8"
                ),
                source=SourceMedia(
                    format="matroska,webm",
                    codec="opus",
                    sample_rate=48000,
                    channels=1,
                    duration_ms=4200,
                ),
                latency_ms=10,
            )

    stub = Hearing()
    monkeypatch.setattr(notebook, "transcribe", stub)
    return stub


def recording() -> dict:
    return {"audio": ("say.webm", b"not really audio", "audio/webm")}


async def say(client, **form):
    form = {
        key: str(value).lower() if isinstance(value, bool) else value
        for key, value in form.items()
    }
    return await client.post(
        "/captures", data={"app": "Mail", **form}, files=recording()
    )


async def type_(client, text, **form):
    form = {
        key: str(value).lower() if isinstance(value, bool) else value
        for key, value in form.items()
    }
    return await client.post("/captures", data={"text": text, **form})


async def count(db_session, model) -> int:
    return await db_session.scalar(select(func.count(model.id)))


# ── Making one ──────────────────────────────────────────────────────────────


async def test_the_notebook_needs_an_account(client):
    assert (await client.get("/captures")).status_code == 401
    assert (await client.post("/captures", data={"text": "hola"})).status_code == 401


async def test_spanish_said_aloud_comes_back_organized_kept_as_text_and_never_as_audio(
    client, account, db_session, hearing, model, writer
):
    assets = await count(db_session, AudioAsset)

    response = await say(client)

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["mode"], body["via"], body["chosen"]) == (
        "translate",
        "voice",
        "organized",
    )
    assert body["text"] == ORGANIZED
    assert body["versions"] == {"organized": ORGANIZED, "direct": None}
    assert body["dropped"]["organized"] == []
    # "Laura" opens the sentence, and is known once the English used it: kept too.
    assert body["kept"] == ["Laura", "Acme", "14"]
    assert body["language"] == {
        "language": "es",
        "by": "recogniser",
        "scores": {"es": 0.97},
        "confidences": {},
    }
    assert body["app"] == "Mail"
    assert body["state"] == "to_practise"
    assert hearing.calls == [{"language": "es,en", "task": None, "url": ASR_MULTI_URL}]
    assert model.kinds == ["organized"], "one model call before the reply"
    assert writer.launched == [body["id"]]
    stored = await db_session.get(Capture, body["id"])
    assert stored.source_text == SPANISH
    assert stored.duration_ms == 4200
    assert await count(db_session, AudioAsset) == assets


async def test_the_other_version_and_the_phrases_are_written_behind_the_reply(
    client, account, hearing, model, writer
):
    made = (await say(client)).json()

    await writer.drain()
    body = (await client.get(f"/captures/{made['id']}")).json()

    assert body["versions"] == {"organized": ORGANIZED, "direct": DIRECT}
    assert body["dropped"]["direct"] == []
    assert [(p["source"], p["english"]) for p in body["phrases"]] == [
        ("te escribo para avisarte", "a quick heads-up"),
        ("se va a retrasar", "will be delayed"),
    ]
    assert model.kinds == ["organized", "direct", "phrases"]


async def test_a_phrase_counts_the_other_captures_whose_english_uses_it(
    client, account, hearing, model, writer
):
    first = (await say(client)).json()
    await say(client)
    await writer.drain()

    phrases = (await client.get(f"/captures/{first['id']}")).json()["phrases"]

    assert {p["english"]: p["elsewhere"] for p in phrases} == {
        "a quick heads-up": 1,
        "will be delayed": 1,
    }


async def test_direct_goes_on_the_clipboard_when_it_is_the_one_asked_for(
    client, account, hearing, model
):
    body = (await say(client, version="direct")).json()

    assert (body["chosen"], body["text"]) == ("direct", DIRECT)


async def test_typed_spanish_is_told_by_its_words_and_translated(
    client, account, model
):
    body = (await type_(client, SPANISH, via="typed")).json()

    assert (body["mode"], body["via"], body["chosen"]) == (
        "translate",
        "typed",
        "organized",
    )
    assert body["language"]["by"] == "words"
    assert model.calls[0][-1].content.startswith("The person wrote:")


async def test_the_switch_overrides_the_words(client, account, model):
    body = (await type_(client, "Laura OK, thanks", mode="translate")).json()

    assert body["mode"] == "translate"
    assert body["language"] == {
        "language": "es",
        "by": "switch",
        "scores": {},
        "confidences": {},
    }


async def test_typed_english_is_corrected_with_its_fixes_and_counted_as_writing(
    client, account, db_session, model, writer
):
    body = (await type_(client, ENGLISH_TYPED, via="copied")).json()

    assert (body["mode"], body["chosen"]) == ("check", "corrected")
    assert body["text"] == "I received your message and I will call you tomorrow."
    assert [(f["original"], f["correction"], f["counted"]) for f in body["fixes"]] == [
        ("recieved", "received", True),
        ("tomorow", "tomorrow", True),
    ]
    assert body["fixes"][0]["label"] == "spelling"
    assert body["state"] == "practised"
    assert body["practised"] == 1
    assert body["attempts"][0]["counted"] == 2
    attempt = await db_session.scalar(
        select(CaptureAttempt).where(CaptureAttempt.capture_id == body["id"])
    )
    errors = (
        await db_session.scalars(
            select(WrittenError).where(WrittenError.attempt_id == attempt.id)
        )
    ).all()
    assert [(e.category, e.detector, e.confidence) for e in errors] == [
        ("SPELLING", "dictionary", 1.0),
        ("SPELLING", "dictionary", 1.0),
    ]
    assert body["box"] == 1
    due = datetime.fromisoformat(body["due_at"])
    assert timedelta(hours=23) < due - datetime.now(timezone.utc) < timedelta(hours=25)
    assert changed(body["changes"]["corrected"]) == [
        ("recieved", "received"),
        ("tomorow.", "tomorrow."),
    ]


def changed(steps: list[dict]) -> list[tuple]:
    """The steps whose words differ, without case or punctuation, as (said, version)."""

    def bare(word):
        return " ".join(normalise(word or ""))

    return [
        (s["said"], s["version"])
        for s in steps
        if bare(s["said"]) != bare(s["version"])
    ]


async def test_polished_follows_behind_a_check(client, account, model, writer):
    made = (await type_(client, ENGLISH_TYPED)).json()
    assert made["versions"] == {"corrected": made["text"], "polished": None}
    assert list(made["changes"]) == ["corrected"]

    await writer.drain()

    later = (await client.get(f"/captures/{made['id']}")).json()
    assert later["versions"]["polished"] == POLISHED
    assert changed(later["changes"]["polished"]) == [
        ("recieved", "received"),
        ("I", None),
        ("tomorow.", "tomorrow"),
        (None, "morning."),
    ]


def test_a_version_beside_what_was_said_marks_only_the_words_it_changed():
    said = "I'm going to speak about my date and then focus on new implementation"
    version = "I'm going to speak about my day, and then focus on new implementations"

    steps = notebook.word_changes(said, version)

    assert [(s.said, s.version) for s in steps if s.said != s.version] == [
        ("date", "day,"),
        ("implementation", "implementations"),
    ]
    assert [s.version for s in steps if s.version] == version.split()
    assert [s.said for s in steps if s.said] == said.split()


async def test_a_translation_has_no_word_changes_and_a_check_counts_its_fixes(
    client, account, hearing, model
):
    translated = (await say(client)).json()
    assert translated["changes"] == {}

    await type_(client, ENGLISH_TYPED, via="copied")
    items = (await client.get("/captures")).json()["items"]
    assert [(i["mode"], i["fixes"]) for i in items] == [("check", 2), ("translate", 0)]


async def test_a_preference_for_each_mode_is_used_by_the_mode_it_fits(
    client, account, hearing, model
):
    spanish = (await say(client, version="direct,polished")).json()
    hearing.queue.append((ENGLISH_SAID, "en"))
    english = (await say(client, version="direct,polished")).json()

    assert (spanish["mode"], spanish["chosen"]) == ("translate", "direct")
    assert (english["mode"], english["chosen"]) == ("check", "polished")


async def test_polished_goes_on_the_clipboard_when_asked_for(client, account, model):
    body = (await type_(client, ENGLISH_TYPED, version="polished")).json()

    assert (body["chosen"], body["text"]) == ("polished", POLISHED)


async def test_english_said_aloud_is_checked_shown_and_never_counted(
    client, account, db_session, hearing, model
):
    hearing.queue.append((ENGLISH_SAID, "en"))
    attempts, errors = await count(db_session, CaptureAttempt), await count(
        db_session, WrittenError
    )

    body = (await say(client)).json()

    assert (body["mode"], body["via"]) == ("check", "voice")
    assert body["fixes"] == [] or all(not f["counted"] for f in body["fixes"])
    assert body["state"] == "to_practise"
    assert await count(db_session, CaptureAttempt) == attempts
    assert await count(db_session, WrittenError) == errors


async def test_english_heard_both_ways_is_checked_and_says_how_sure_each_was(
    client, account, hearing, model
):
    """An accent the detection took for Spanish: the recogniser heard it in both and kept
    the English, the transcript it was surer of, and the capture carries both figures.
    """
    hearing.queue.append((ENGLISH_SAID, "en"))
    hearing.confidences = {"es": 0.751, "en": 0.937}

    body = (await say(client)).json()

    assert body["mode"] == "check"
    assert body["language"] == {
        "language": "en",
        "by": "recogniser",
        "scores": {"en": 0.97},
        "confidences": {"es": 0.751, "en": 0.937},
    }


async def test_a_spoken_checks_fixes_are_kept_to_show_and_count_nowhere(
    client, account, db_session, hearing, model
):
    model.replies_by_kind["errors"] = {
        "errors": [
            {
                "category": "PREPOSITION",
                "subcategory": "missing",
                "original": "waiting the data",
                "correction": "waiting for the data",
                "explanation": "You wait for something.",
                "confidence": 0.9,
            }
        ]
    }
    hearing.queue.append(("we are still waiting the data", "en"))
    errors = await count(db_session, WrittenError)

    body = (await say(client)).json()

    assert [(f["original"], f["counted"]) for f in body["fixes"]] == [
        ("waiting the data", False)
    ]
    again = (await client.get(f"/captures/{body['id']}")).json()
    assert [f["correction"] for f in again["fixes"]] == ["waiting for the data"]
    assert await count(db_session, WrittenError) == errors


async def test_a_paused_capture_writes_nothing(
    client, account, db_session, hearing, model, writer
):
    before = [
        await count(db_session, table)
        for table in (Capture, CaptureAttempt, WrittenError)
    ]

    spoken = await say(client, save=False)
    typed = await type_(client, ENGLISH_TYPED, save=False)

    assert spoken.status_code == typed.status_code == 200
    assert spoken.json()["id"] is None and spoken.json()["saved"] is False
    assert spoken.json()["text"] == ORGANIZED
    assert (
        typed.json()["text"] == "I received your message and I will call you tomorrow."
    )
    assert [f["counted"] for f in typed.json()["fixes"]] == [False, False]
    after = [
        await count(db_session, table)
        for table in (Capture, CaptureAttempt, WrittenError)
    ]
    assert after == before
    assert writer.launched == []


async def test_with_the_model_down_speech_gets_the_recognisers_rough_english(
    client, account, hearing, model
):
    model.down.add("organized")

    body = (await say(client)).json()

    assert (body["chosen"], body["text"]) == ("rough", ROUGH)
    assert body["versions"]["rough"] == ROUGH
    assert "rough" in body["notes"][0]
    assert [call["task"] for call in hearing.calls] == [None, "translate"]


async def test_with_the_model_down_a_typed_translation_is_refused_and_nothing_kept(
    client, account, db_session, model
):
    model.down.add("organized")
    captures = await count(db_session, Capture)

    response = await type_(client, SPANISH)

    assert response.status_code == 503
    assert "not answering" in response.json()["detail"]
    assert await count(db_session, Capture) == captures


async def test_with_the_model_down_a_check_is_the_dictionarys_and_says_so(
    client, account, model
):
    model.down.update({"errors", "polished"})

    body = (await type_(client, ENGLISH_TYPED, version="polished")).json()

    assert body["chosen"] == "corrected"
    assert {f["detector"] for f in body["fixes"]} == {"dictionary"}
    assert any("did not answer" in note for note in body["notes"])


async def test_nothing_heard_or_typed_is_a_422_and_nothing_is_kept(
    client, account, db_session, hearing, model
):
    hearing.queue.append(("   ", "es"))
    captures = await count(db_session, Capture)

    assert (await say(client)).status_code == 422
    assert (await type_(client, " ... ")).status_code == 422
    assert await count(db_session, Capture) == captures


async def test_the_recogniser_down_is_a_503_that_says_nothing_was_saved(
    client, account, hearing, model
):
    hearing.error = AsrUnavailable("ConnectError")

    response = await say(client)

    assert response.status_code == 503
    assert "Nothing was saved" in response.json()["detail"]


@pytest.mark.parametrize(
    ("form", "files"),
    [
        ({"text": "hola"}, {"audio": ("a.webm", b"x", "audio/webm")}),
        ({}, None),
        ({"text": "hola", "mode": "guess"}, None),
        ({"text": "hola", "version": "poem"}, None),
        ({"text": "hola", "via": "voice"}, None),
    ],
)
async def test_a_malformed_request_is_a_422(client, account, model, form, files):
    assert (await client.post("/captures", data=form, files=files)).status_code == 422


# ── The Notebook ────────────────────────────────────────────────────────────


async def test_a_version_is_written_on_demand_and_one_it_cannot_have_is_a_409(
    client, account, hearing, model
):
    made = (await say(client)).json()

    written = await client.post(f"/captures/{made['id']}/versions/direct")
    refused = await client.post(f"/captures/{made['id']}/versions/polished")

    assert written.status_code == 200
    assert written.json()["versions"]["direct"] == DIRECT
    assert refused.status_code == 409


async def test_the_list_is_newest_first_filtered_and_counted(
    client, account, hearing, model
):
    first = (await say(client, app="Mail")).json()
    second = (await say(client, app="Slack")).json()
    typed = (await type_(client, ENGLISH_TYPED, app="Slack")).json()

    everything = (await client.get("/captures")).json()
    slack = (await client.get("/captures", params={"app": "Slack"})).json()
    unpractised = (
        await client.get("/captures", params={"state": "to_practise"})
    ).json()
    found = (await client.get("/captures", params={"q": "tomorrow"})).json()
    checked = (await client.get("/captures", params={"mode": "check"})).json()

    assert [item["id"] for item in everything["items"]] == [
        typed["id"],
        second["id"],
        first["id"],
    ]
    assert everything["matching"] == 3
    assert set(everything["apps"]) == {"Mail", "Slack"}
    assert [item["id"] for item in slack["items"]] == [typed["id"], second["id"]]
    assert [item["id"] for item in unpractised["items"]] == [second["id"], first["id"]]
    assert [item["id"] for item in found["items"]] == [typed["id"]]
    assert [item["id"] for item in checked["items"]] == [typed["id"]]
    assert everything["counts"] == {
        "total": 3,
        "this_week": 3,
        "practised_this_week": 1,
        "clean_this_week": 0,
        "due": 0,
        "to_practise": 2,
    }


async def test_writing_it_yourself_checks_it_and_moves_it_through_the_boxes(
    client, account, db_session, hearing, model
):
    made = (await say(client)).json()

    wrong = await client.post(
        f"/captures/{made['id']}/attempts",
        json={"text": "Laura, the client report will be late untill Thursday 14."},
    )
    right = await client.post(
        f"/captures/{made['id']}/attempts",
        json={
            "text": "Hi Laura, the client report will be delayed until Thursday the 14th."
        },
    )

    assert wrong.status_code == right.status_code == 201
    first, second = wrong.json(), right.json()
    assert [(e["original"], e["counted"]) for e in first["errors"]] == [
        ("untill", True)
    ]
    assert (first["box_before"], first["box"]) == (0, 1)
    assert (second["counted"], second["box_before"], second["box"]) == (0, 1, 2)
    due = datetime.fromisoformat(second["due_at"]) - datetime.now(timezone.utc)
    assert timedelta(days=2, hours=23) < due < timedelta(days=3, hours=1)
    assert second["compared_with"] == "organized"
    assert second["compared_text"] == ORGANIZED
    assert {"expected": "until", "written": "untill"} in first["words"]
    body = (await client.get(f"/captures/{made['id']}")).json()
    assert body["practised"] == 2 and body["state"] == "practised"
    assert [a["counted"] for a in body["attempts"]] == [1, 0]


async def test_an_attempt_with_nothing_in_it_is_a_422(client, account, hearing, model):
    made = (await say(client)).json()

    assert (
        await client.post(f"/captures/{made['id']}/attempts", json={"text": " ."})
    ).status_code == 422


async def test_saying_it_yourself_compares_what_was_heard_and_stores_nothing(
    client, account, db_session, hearing, recogniser, model
):
    made = (await say(client, version="direct")).json()
    recogniser.append(
        "Laura I'm writing to let you know that the client report is going to be late"
    )
    attempts = await count(db_session, CaptureAttempt)

    response = await client.post(
        f"/captures/{made['id']}/say", files={"file": ("me.webm", b"x", "audio/webm")}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["compared_with"] == "direct"
    assert body["expected"] == DIRECT
    assert body["matched"] > 10 and body["missed"] > 0
    assert "Nothing is stored" in body["caveat"]
    assert await count(db_session, CaptureAttempt) == attempts


async def test_deleting_one_takes_its_attempts_mistakes_and_phrases_with_it(
    client, account, db_session, hearing, model, writer
):
    made = (await say(client)).json()
    await writer.drain()
    await client.post(
        f"/captures/{made['id']}/attempts", json={"text": "I recieved it untill now."}
    )

    response = await client.delete(f"/captures/{made['id']}")

    assert response.status_code == 204
    assert (await client.get(f"/captures/{made['id']}")).status_code == 404
    left = await db_session.scalar(
        select(func.count(CaptureAttempt.id)).where(
            CaptureAttempt.capture_id == made["id"]
        )
    )
    phrases = await db_session.scalar(
        select(func.count(CapturePhrase.id)).where(
            CapturePhrase.capture_id == made["id"]
        )
    )
    orphans = await db_session.scalar(
        select(func.count(WrittenError.id)).where(
            WrittenError.attempt_id.not_in(select(CaptureAttempt.id))
        )
    )
    assert (left, phrases, orphans) == (0, 0, 0)


async def test_deleting_all_of_them_leaves_another_accounts(
    client, other_client, account, hearing, model
):
    await say(client)
    await type_(client, ENGLISH_TYPED)
    await register_account(other_client)
    theirs = (await type_(other_client, SPANISH)).json()

    response = await client.delete("/captures")

    assert response.json() == {"deleted": 2}
    assert (await client.get("/captures")).json()["matching"] == 0
    assert (await other_client.get(f"/captures/{theirs['id']}")).status_code == 200


async def test_another_accounts_capture_is_not_found(
    client, other_client, account, hearing, model
):
    made = (await say(client)).json()
    await register_account(other_client)
    url = f"/captures/{made['id']}"

    assert (await other_client.get(url)).status_code == 404
    assert (await other_client.post(f"{url}/versions/direct")).status_code == 404
    assert (
        await other_client.post(f"{url}/attempts", json={"text": "Hi"})
    ).status_code == 404
    assert (
        await other_client.post(
            f"{url}/say", files={"file": ("me.webm", b"x", "audio/webm")}
        )
    ).status_code == 404
    assert (await other_client.delete(url)).status_code == 404
    assert (await client.get(url)).status_code == 200


async def test_the_warm_up_answers_at_once_and_asks_the_model_to_load(
    client, account, model
):
    response = await client.post("/captures/warm")
    await asyncio.sleep(0)

    assert response.status_code == 202
    assert response.json() == {"warming": "gemma4:e4b"}
    assert model.warmed == 1


# ── Progress and the history file ───────────────────────────────────────────


async def test_written_mistakes_are_counted_as_writing_and_never_move_a_spoken_figure(
    client, account, hearing, model
):
    before = (await client.get("/progress")).json()
    made = (await say(client)).json()
    await type_(client, ENGLISH_TYPED)
    await client.post(
        f"/captures/{made['id']}/attempts",
        json={
            "text": "Laura, I recieved the data untill now and the report is late, " * 4
        },
    )

    after = (await client.get("/progress")).json()

    assert after["families"] == before["families"]
    assert after["totals"] == before["totals"]
    assert after["repertoire"] == before["repertoire"]
    writing = after["writing"]
    assert writing["totals"]["captures"] == 2
    assert writing["totals"]["attempts"] == 2
    assert writing["totals"]["counted"] == 2 + 8
    series = {s["metric"]: s for s in writing["series"]}
    this_week = series["captures"]["points"][-1]
    assert this_week["value"] == 2.0
    rate = series["written_errors_per_100_words"]["points"][-1]
    assert rate["value"] == round(10 * 100 / writing["totals"]["words"], 2)
    assert "speech is measured in conversations" in writing["caveat"]


async def test_the_history_file_carries_the_captures_and_what_was_written_of_them(
    client, account, hearing, model
):
    made = (await say(client)).json()
    await client.post(
        f"/captures/{made['id']}/attempts", json={"text": "I recieved it."}
    )

    document = (await client.get("/progress/export")).json()

    [capture] = document["captures"]
    assert capture["source_text"] == SPANISH
    assert capture["versions"]["organized"] == ORGANIZED
    assert capture["attempts"][0]["errors"][0]["correction"] == "received"
