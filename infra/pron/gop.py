"""Forced alignment and Goodness of Pronunciation. PRD §6.2 / §7.4.

    GOP(p) = log P(p | O_seg) − max over q of log P(q | O_seg)     (Witt & Young 2000)

Both terms are averaged over the frames of the aligned segment, so **GOP ≤ 0 by
construction**, and GOP = 0 means the canonical phone was itself the best-scoring phone
over its own span. Frame posteriors come from a wav2vec2 CTC phoneme model; the segment
boundaries come from CTC forced alignment against the canonical phone sequence.

m0 measured the separation this is built to detect: a phone the speaker did not produce
drops **8.14 nats** below one they did, Cohen's d = 8.26, on real human speech, with the
competing phone named correctly in 10 cases out of 10.

Three things here are deliberately not what the spike did.

**The competitor maximum is taken over phones, not over every token.** CTC's blank is not
a phone, and a segment where blank scores highest is a segment that was short or quiet —
not one where the speaker produced silence instead of a /θ/. Reporting ``<pad>`` as "what
you said instead" would be a claim about speech the acoustic model never made, which is
what invariant I2 forbids. The spike's arithmetic is still computed, as ``gop_all_tokens``,
so the size of this deviation is a measured number in docs/decisions/0005 rather than an
assurance in a comment.

**Spans come from ``torchaudio.functional.merge_tokens`` rather than a hand-walked
alignment.** The spike walked the frame labels itself and had to defend against emitting
more spans than there were targets. merge_tokens returns exactly one span per target, so
that whole class of off-by-one is gone, and the code asserts the count rather than
skipping the overflow.

**Alignment failure is distinguished from a bad recording.** If the audio is shorter than
the phone sequence needs, CTC cannot align and torchaudio raises. That is not a broken
file — it is a person who read three words of a seventy-nine word passage — and it has to
reach the user as that, not as a 500.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import torch
import torchaudio

import phone_map as pm
from g2p import Word, flatten

# wav2vec2 base stride: 320 samples at 16 kHz. Frame index → milliseconds.
FRAME_MS = 20.0
SAMPLE_RATE = 16000

# Everything in the vocabulary that is not a phone. The competitor maximum skips these:
# a GOP that compares /θ/ against the blank is measuring duration, not pronunciation.
_SPECIAL = {"|", " "}


def phone_token_ids(vocab: dict[str, int]) -> torch.Tensor:
    """Ids of the tokens that are actually phones, as a tensor for indexing."""
    ids = [
        index
        for token, index in vocab.items()
        if token not in _SPECIAL and not (token.startswith("<") and token.endswith(">"))
    ]
    return torch.tensor(sorted(ids), dtype=torch.long)


PHONE_IDS = phone_token_ids(pm.VOCAB)


class AlignmentError(ValueError):
    """The phone sequence could not be aligned to this audio. A 422, never a 500."""


def log_posteriors(model, audio: np.ndarray) -> torch.Tensor:
    """16 kHz mono float32 → ``[T, C]`` log-softmax over the phone vocabulary."""
    with torch.inference_mode():
        logits = model(torch.from_numpy(audio).unsqueeze(0)).logits
    return torch.log_softmax(logits, dim=-1)[0]


def score(model, audio: np.ndarray, words: list[Word]) -> list[dict[str, Any]]:
    """One recording against one canonical phone sequence → one row per phone.

    Rows are shaped exactly like the ``phoneme_scores`` table (plan §5). The API stores
    them without reshaping, which is why the field names here are the column names there
    and not a wire format that has to be translated twice.
    """
    flat = flatten(words)
    if not flat:
        raise AlignmentError("the reference text produced no phones to score")

    log_probs = log_posteriors(model, audio)

    # Alignment targets use the PRIMARY token for each phone. The acceptable-variant set
    # is applied when *scoring*, not when aligning: /t/ and the American flap are the
    # same target for the purpose of finding where the phone is, and two different
    # answers to the question of whether it was produced well.
    targets = torch.tensor(
        [[pm.map_phone(phone, pm.TABLE)[0] for *_, phone in flat]], dtype=torch.int32
    )

    if log_probs.shape[0] < targets.shape[1]:
        raise AlignmentError(
            f"the recording is {log_probs.shape[0]} frames "
            f"({log_probs.shape[0] * FRAME_MS / 1000:.1f} s) but the passage needs at "
            f"least {targets.shape[1]}. Either the recording is much shorter than the "
            f"text, or it stopped early."
        )

    try:
        aligned, scores = torchaudio.functional.forced_align(
            log_probs.unsqueeze(0), targets, blank=0
        )
    except RuntimeError as exc:
        raise AlignmentError(f"forced alignment failed: {exc}") from exc

    spans = torchaudio.functional.merge_tokens(aligned[0], scores[0], blank=0)
    if len(spans) != len(flat):
        # An invariant, not an expected condition: merge_tokens returns one span per
        # target. If that stops being true the phone-to-word attribution below is wrong,
        # and wrong attribution is a heatmap that tints the wrong word.
        raise AlignmentError(
            f"alignment produced {len(spans)} spans for {len(flat)} phones"
        )

    rows: list[dict[str, Any]] = []
    for position, span in enumerate(spans):
        word_idx, surface, phone_idx, phone = flat[position]
        segment = log_probs[span.start : span.end]
        if segment.shape[0] == 0:
            continue

        mean_lp = segment.mean(dim=0)

        # The canonical term: the best-scoring *acceptable* realisation of this phone.
        candidates = pm.map_phone(phone, pm.TABLE)
        canonical = max(float(mean_lp[c]) for c in candidates)

        # The competitor term, over phones only. `PHONE_IDS` indexes the vocabulary, so
        # `winner` is an index into that subset and has to be mapped back.
        phone_lp = mean_lp[PHONE_IDS]
        winner = int(phone_lp.argmax())
        best_id = int(PHONE_IDS[winner])
        best_lp = float(phone_lp[winner])

        # The spike's arithmetic, kept so the deviation above is measurable rather than
        # asserted. Not stored; reported.
        best_any = float(mean_lp.max())

        recognized = pm.ID_TO_TOKEN.get(best_id)
        rows.append(
            {
                "word": surface,
                "word_idx": word_idx,
                "phone_idx": phone_idx,
                "canonical_phone": phone,
                "recognized_phone": recognized,
                "start_ms": int(span.start * FRAME_MS),
                "end_ms": int(span.end * FRAME_MS),
                "gop": round(canonical - best_lp, 4),
                "posterior": round(math.exp(min(canonical, 0.0)), 5),
                # Diagnostics. The API drops these before storing; they exist so that a
                # surprising score can be explained without re-running the model.
                "frames": span.end - span.start,
                "gop_all_tokens": round(canonical - best_any, 4),
                # m0 §2: eSpeak emits r-coloured composites as single tokens where
                # g2p_en emits two ARPAbet phones, so segmentation can differ around
                # rhotics even though every symbol maps. Flagged rather than corrected,
                # because the right correction is a decision that needs this count.
                "r_composite": recognized in pm.R_COMPOSITES,
            }
        )

    return rows


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The aggregates worth computing once here rather than four times downstream.

    ``percentile_5`` is the operating point m0 settled on for Q2: the GOP below which 5 %
    of *this* reading's phones fall. It is reported per attempt because a threshold is a
    property of a speaker and a corpus, and the one number this service must never do is
    hand back a constant that looks calibrated.
    """
    if not rows:
        return {"phones": 0}
    gops = sorted(row["gop"] for row in rows)
    mean = sum(gops) / len(gops)
    return {
        "phones": len(rows),
        "mean_gop": round(mean, 4),
        "median_gop": round(gops[len(gops) // 2], 4),
        "percentile_5": round(_percentile(gops, 0.05), 4),
        "r_composites": sum(1 for row in rows if row["r_composite"]),
        "blank_dominated": sum(
            1 for row in rows if row["gop_all_tokens"] < row["gop"] - 1e-9
        ),
    }


def _percentile(sorted_values: list[float], q: float) -> float:
    """Linear interpolation, matching the m0 spike's `analyze.py` exactly."""
    if not sorted_values:
        return float("nan")
    k = (len(sorted_values) - 1) * q
    low = int(k)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (k - low)
