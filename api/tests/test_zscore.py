"""Where a reading sits against the speaker's own history, and when it refuses to say.

The z-score is the only reason a pronunciation number is comparable across weeks: the raw
score moves with the microphone, the room and the distance from it, so what is plotted has
to be a distance from the same speaker's own recent readings rather than a value.

Every test here is about the refusals. Getting the arithmetic right is one line; the
question that decides whether the chart lies is when there is not enough history to
produce a number at all, and the wrong answer to that is 0.0 — which draws a speaker
sitting exactly on a baseline that does not exist.
"""

import statistics

import pytest

from services.rollup import unstressed, zscore


def test_a_value_is_expressed_in_standard_deviations_of_the_baseline():
    baseline = [-2.0, -4.0, -3.0, -3.0]
    spread = statistics.stdev(baseline)
    mean = statistics.fmean(baseline)

    assert zscore(-1.0, baseline) == pytest.approx(round((-1.0 - mean) / spread, 3))


def test_better_than_the_baseline_is_positive():
    """Goodness-of-pronunciation is at most zero and larger is better, so an improvement
    has to come out positive. A sign error here would render every improving sound as a
    weakness and put it at the top of the practice list."""
    assert zscore(-1.0, [-3.0, -4.0, -3.5]) > 0
    assert zscore(-6.0, [-3.0, -4.0, -3.5]) < 0


def test_a_single_prior_reading_is_not_a_baseline():
    """One reading has no spread, so there is nothing to express a distance in. A first
    month of practice is entirely this case."""
    assert zscore(-2.0, [-3.0]) is None


def test_no_prior_readings_is_not_a_baseline_either():
    assert zscore(-2.0, []) is None


def test_a_baseline_with_no_spread_refuses_rather_than_dividing_by_zero():
    """Identical prior readings are not a tight distribution — they are a sample too
    small to have shown its variation yet. The honest answer is that there is no scale to
    measure this against, not an infinite one."""
    assert zscore(-2.0, [-3.0, -3.0, -3.0]) is None


def test_sitting_exactly_on_the_baseline_is_zero_rather_than_nothing():
    """Zero and None must not be the same value: this one means "measured, and unchanged",
    which is a real finding about a speaker."""
    assert zscore(-3.0, [-2.0, -4.0]) == 0.0


def test_the_baseline_is_a_sample_deviation_not_a_population_one():
    """The prior readings are a sample of how this speaker says the sound, not every
    reading they will ever make. Population spread would be smaller and every z would
    come out further from zero than the data supports."""
    baseline = [-2.0, -4.0]
    assert zscore(-1.0, baseline) == pytest.approx(
        round((-1.0 - statistics.fmean(baseline)) / statistics.stdev(baseline), 3)
    )


@pytest.mark.parametrize(
    ("stored", "expected"),
    [("AH0", "AH"), ("AH1", "AH"), ("AA2", "AA"), ("TH", "TH"), ("NG", "NG")],
)
def test_stress_is_folded_away_before_anything_is_counted(stored, expected):
    """The aligner scores `AH0` and `AH1` separately; a learner is told to work on a
    sound. Leaving the digits on would split one phone's history into three series, each
    thin enough to be suppressed by its own sample gate — so the trend would vanish for
    exactly the vowels that appear most."""
    assert unstressed(stored) == expected
