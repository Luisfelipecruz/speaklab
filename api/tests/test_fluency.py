"""Fluency arithmetic, checked against timings computed by hand.

Every number here is one somebody can verify with a calculator, which is the point: these
are the figures a learner watches over months, and a metric whose expected value is
whatever the code returns is not a metric anybody can dispute.
"""

import pytest

from config import FLUENCY_PAUSE_MS
from services.fluency import FILLERS, analyse


def word(text: str, start_ms: int, end_ms: int, logprob: float = -0.1) -> dict:
    return {"w": text, "start_ms": start_ms, "end_ms": end_ms, "logprob": logprob}


def evenly_spaced(count: int, each_ms: int = 500) -> list[dict]:
    """`count` words, back to back, with no gap between any two."""
    return [word(f"w{i}", i * each_ms, (i + 1) * each_ms) for i in range(count)]


# ── Rates ───────────────────────────────────────────────────────────────────


def test_speech_rate_is_words_over_the_speaking_span():
    """Ten words in five seconds is 120 wpm, and it is arithmetic rather than a fit."""
    result = analyse(evenly_spaced(10, each_ms=500))
    assert result.word_count == 10
    assert result.speech_rate_wpm == 120.0


def test_leading_silence_is_not_counted_as_speaking_time():
    """The recorder starts before the speaker does. Counting the gap before the first
    word as slow speech would make somebody look hesitant for being slow with a button —
    so the span runs from the first word, and the silence is reported separately."""
    words = [word("hello", 3000, 3500), word("there", 3500, 4000)]
    result = analyse(words)
    assert result.speech_rate_wpm == 120.0
    assert result.response_latency_ms == 3000


def test_articulation_rate_removes_the_pauses_and_speech_rate_keeps_them():
    """The two are kept apart because a speaker who gets faster only by pausing less has
    not learned to articulate any faster."""
    words = [
        word("one", 0, 500),
        word("two", 500, 1000),
        # A two-second pause, well over the threshold.
        word("three", 3000, 3500),
        word("four", 3500, 4000),
    ]
    result = analyse(words)
    assert result.speech_rate_wpm == 60.0  # 4 words in 4.0 s
    assert result.articulation_rate == 120.0  # 4 words in 2.0 s of phonated time
    assert result.articulation_rate > result.speech_rate_wpm


def test_a_turn_with_no_pauses_has_the_same_two_rates():
    result = analyse(evenly_spaced(6))
    assert result.speech_rate_wpm == result.articulation_rate
    assert result.pause_ratio == 0.0


# ── What counts as a pause ──────────────────────────────────────────────────


def test_a_gap_below_the_threshold_is_not_a_pause():
    """Word boundaries out of the recogniser are accurate to tens of milliseconds.
    Counting every small gap would measure its timestamp granularity."""
    just_under = FLUENCY_PAUSE_MS - 1
    words = [word("one", 0, 500), word("two", 500 + just_under, 1000 + just_under)]
    result = analyse(words)
    assert result.pause_ratio == 0.0
    assert result.mean_length_run == 2.0


def test_a_gap_at_the_threshold_is_a_pause():
    words = [
        word("one", 0, 500),
        word("two", 500 + FLUENCY_PAUSE_MS, 1000 + FLUENCY_PAUSE_MS),
    ]
    result = analyse(words)
    assert result.pause_ratio > 0
    assert result.mean_length_run == 1.0


def test_all_three_pause_metrics_use_one_definition():
    """Articulation rate, pause ratio and mean length of run have to agree about what a
    pause is, or two of them describe a turn the third did not hear."""
    words = [
        word("one", 0, 500),
        word("two", 500, 1000),
        word("three", 2000, 2500),  # a 1000 ms pause
        word("four", 2500, 3000),
    ]
    result = analyse(words)
    assert result.pause_ratio == pytest.approx(1000 / 3000, abs=1e-4)
    assert result.mean_length_run == 2.0
    assert result.articulation_rate == 120.0


def test_mean_length_of_run_is_words_over_runs():
    """Two long unbroken answers and one delivered in six-word bursts can share a speech
    rate and differ entirely here."""
    words = [
        word("a", 0, 200),
        word("b", 200, 400),
        word("c", 1000, 1200),  # pause
        word("d", 1200, 1400),
        word("e", 1400, 1600),
        word("f", 2400, 2600),  # pause
    ]
    result = analyse(words)
    assert result.mean_length_run == 2.0  # six words, three runs


# ── Fillers ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("filler", sorted(FILLERS))
def test_every_filler_in_the_list_is_counted(filler):
    result = analyse([word(filler, 0, 300), word("yes", 300, 600)])
    assert result.filler_count == 1


def test_punctuation_and_case_do_not_hide_a_filler():
    """The recogniser attaches punctuation to the token and capitalises what it thinks is
    a sentence start, so a bare string comparison would miss most of them."""
    result = analyse([word("Um,", 0, 300), word("yes", 300, 600)])
    assert result.filler_count == 1


def test_like_is_not_counted_as_a_filler():
    """ "like a dog or a cat" is an ordinary preposition, and no rule over a word list can
    tell it from the discourse marker. Missing a real filler is better than scoring a
    correct sentence as hesitation."""
    words = [
        word("like", 0, 300),
        word("a", 300, 500),
        word("dog", 500, 900),
    ]
    assert analyse(words).filler_count == 0


# ── Turns with nothing in them ──────────────────────────────────────────────


def test_a_turn_with_no_words_has_no_rates_rather_than_rates_of_zero():
    """A turn with nothing in it has no fluency to measure. Zero would say the speaker
    spoke at zero words a minute, which is a different claim."""
    result = analyse([])
    assert result.word_count == 0
    assert result.speech_rate_wpm is None
    assert result.articulation_rate is None
    assert result.mean_length_run is None


def test_none_is_treated_as_an_unmeasured_turn():
    assert analyse(None).speech_rate_wpm is None


def test_words_without_timings_are_skipped_rather_than_crashing():
    """The column is JSONB, and a stored row may lack a key."""
    words = [{"w": "hello"}, word("there", 0, 500), {"w": "x", "start_ms": "no"}]
    result = analyse(words)
    assert result.word_count == 1


def test_a_single_word_turn_has_a_pause_ratio_of_zero_not_null():
    """It has no span and no pauses. Zero says "none", which is true; null would say "not
    measured", which is not."""
    result = analyse([word("thanks", 100, 100)])
    assert result.pause_ratio == 0.0
    assert result.speech_rate_wpm is None
