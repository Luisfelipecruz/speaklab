"""Joining the sentences of a reply into one file.

Reading this next to `services/audio.py` will look like a contradiction, so it is worth
settling immediately. That module says the API has no media library and cannot open an
audio file, and that remains true of everything a *user* uploads: the API never decodes
a recording, never guesses its format, and takes `duration_ms` and `sample_rate` from
the service that actually decoded it.

This module is the other direction. PRD §9.1's first fallback is to stream the reply out
of the LLM and synthesise it sentence by sentence while the rest is still being written,
which is what makes a long reply fit the turn budget at all — and it produces N little
WAVs where the turn needs one, because `turns.audio_asset_id` is a single reference and
because a browser playing a queue of `<audio>` elements puts an audible gap at every
sentence boundary.

So: no decoding, no format detection, no resampling, no library. `wave` is the standard
library, the inputs are files this system's own voice produced seconds earlier, and the
operation is to copy PCM frames from several containers into one. The parameters are
checked rather than assumed — not because they are expected to differ, but because if
the voice were ever reconfigured mid-reply, the silent version of this bug is a reply
that plays at the wrong pitch from the second sentence on, and there is no test that
notices audio sounding wrong.
"""

import io
import wave


class WavMismatch(Exception):
    """Two parts of one reply disagree about their audio format. Never expected."""


class WavUnreadable(Exception):
    """A part is not a readable WAV. It came from the voice, so this is a protocol skew."""


def concatenate(parts: list[bytes]) -> tuple[bytes, int, int]:
    """One WAV from several. Returns `(wav, sample_rate, duration_ms)`.

    The duration is computed from the frame count that was actually written, not summed
    from the `X-Duration-Ms` headers the service reported. Those two should agree; if
    they ever do not, the frames are the ones that will be played, and a stored duration
    that describes something other than the stored audio is a lie the player will expose.

    A single part is not special-cased into a passthrough. It costs one parse and one
    rewrite of a small buffer, and it means the one-sentence reply — much the most
    common shape — travels the same code path as every other, rather than being the case
    that is never exercised until the day a reply has two sentences.
    """
    if not parts:
        raise WavUnreadable("nothing to concatenate: the reply produced no audio")

    params = None
    frames: list[bytes] = []

    for index, part in enumerate(parts):
        try:
            with wave.open(io.BytesIO(part), "rb") as reader:
                current = reader.getparams()
                frames.append(reader.readframes(reader.getnframes()))
        except (wave.Error, EOFError) as exc:
            raise WavUnreadable(f"part {index} is not a readable WAV: {exc}") from exc

        if params is None:
            params = current
        elif (current.nchannels, current.sampwidth, current.framerate) != (
            params.nchannels,
            params.sampwidth,
            params.framerate,
        ):
            raise WavMismatch(
                f"part {index} is {current.nchannels}ch/{current.sampwidth * 8}bit/"
                f"{current.framerate}Hz but part 0 is {params.nchannels}ch/"
                f"{params.sampwidth * 8}bit/{params.framerate}Hz"
            )

    assert params is not None  # `parts` is non-empty, checked above
    payload = b"".join(frames)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(params.nchannels)
        writer.setsampwidth(params.sampwidth)
        writer.setframerate(params.framerate)
        writer.writeframes(payload)

    frame_count = len(payload) // (params.nchannels * params.sampwidth)
    duration_ms = round(frame_count * 1000 / params.framerate)
    return buffer.getvalue(), params.framerate, duration_ms
