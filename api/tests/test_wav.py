"""Joining per-sentence synthesis into one file.

Small module, and the tests are mostly about the failure it must not have. A reply is
synthesised sentence by sentence so that the voice can work while the model is still
writing, and the pieces are then joined — and if that join ever silently drops frames or
mixes sample rates, the symptom is audio that sounds slightly wrong. Nothing asserts
against a sound. So the arithmetic is asserted instead.
"""

import io
import wave

import pytest

from services.wav import WavMismatch, WavUnreadable, concatenate
from tests.conftest import silent_wav


def frames_of(data: bytes) -> int:
    with wave.open(io.BytesIO(data), "rb") as reader:
        return reader.getnframes()


def test_the_joined_file_has_every_frame_of_its_parts():
    """The one property that cannot be checked by listening: no sample is lost at a
    sentence boundary, and none is duplicated."""
    parts = [silent_wav(100), silent_wav(250), silent_wav(80)]

    joined, sample_rate, duration_ms = concatenate(parts)

    assert frames_of(joined) == sum(frames_of(part) for part in parts)
    assert sample_rate == 22050
    assert duration_ms == pytest.approx(430, abs=2)


def test_the_duration_describes_the_audio_that_was_actually_written():
    """Computed from the frames written, not summed from what the service reported per
    sentence. Where those disagree the frames are what will play, and a stored duration
    that describes something else is a lie the player exposes."""
    joined, _, duration_ms = concatenate([silent_wav(200), silent_wav(200)])

    with wave.open(io.BytesIO(joined), "rb") as reader:
        real_ms = round(reader.getnframes() * 1000 / reader.getframerate())

    assert duration_ms == real_ms


def test_one_part_travels_the_same_path_as_many():
    """A one-sentence reply is much the most common shape. Special-casing it into a
    passthrough would make the joining code the branch that is never exercised until the
    day a reply has two sentences."""
    single = silent_wav(150)
    joined, _, duration_ms = concatenate([single])

    assert frames_of(joined) == frames_of(single)
    assert duration_ms == pytest.approx(150, abs=2)


def test_parts_that_disagree_about_the_sample_rate_are_refused():
    """Joining 22 050 Hz to 16 000 Hz produces a file that plays the second half at the
    wrong pitch. There is no test anywhere that notices audio sounding wrong, so this is
    where it has to be caught."""
    with pytest.raises(WavMismatch, match="22050Hz"):
        concatenate([silent_wav(100, 22050), silent_wav(100, 16000)])


def test_something_that_is_not_a_wav_is_refused_by_the_part_that_is_wrong():
    with pytest.raises(WavUnreadable, match="part 1"):
        concatenate([silent_wav(100), b"<html>502 Bad Gateway</html>"])


def test_nothing_to_join_is_an_error_and_not_an_empty_file():
    """A zero-length WAV would be stored, served, and play as nothing at all — a reply
    that appears to have been spoken and was not."""
    with pytest.raises(WavUnreadable, match="no audio"):
        concatenate([])
