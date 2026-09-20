"""Saying one word aloud, so a named sound can be heard.

Every screen that names a sound has so far only been able to name it. *The "z" at the
end of "is"* tells a speaker which sound to attend to and nothing about what it should
sound like, and the gap between those two is most of the distance between a measurement
and something a person can practise.

**The word is not the caller's to choose.** `services/speakable` holds the rule; this
router holds the consequence, which is that a word outside the set is a 404 with no
explanation. The set is the example words in the phone names, the shipped passages, and
the requester's own scripts — never arbitrary text.

**The voice is pinned here and nowhere else.** This synthesis passes zero for both of
the voice's noise settings, so the same word comes back byte-identical every time. A
reply in a conversation is speech and varies the way speech does; a word offered as
something to imitate is a specimen, and a specimen that changes on every press is not
showing the listener anything they can hold on to.

That determinism is also what makes the caching honest. The audio is a pure function of
the voice, the word and those settings, so the response carries an ETag computed from
exactly those — which means a browser that already has the word is answered **without
synthesising it again**, and nothing has to be stored to achieve that.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from config import PIPER_VOICE, SPEAK_CACHE_SECONDS
from database import get_db
from db_models import User
from dependencies import current_user
from services import speakable
from services.tts_client import TtsError, TtsUnavailable, speak

router = APIRouter(prefix="/speak", tags=["speak"])

# Both of the voice's noise sources, off. Named here rather than passed as bare zeros so
# that the one place the product asks for a repeatable rendering says why.
PINNED_NOISE = 0.0


def _etag(word: str) -> str:
    """The identity of this audio, without producing it.

    Everything that decides the bytes is in the hash, so a match means the caller
    already holds exactly what this route would return. The word is included after
    normalisation, which is why two spellings of the same word share an entry.
    """
    material = f"{PIPER_VOICE}|{word}|{PINNED_NOISE}|{PINNED_NOISE}"
    return '"' + hashlib.sha256(material.encode()).hexdigest()[:32] + '"'


@router.get(
    "/{word}",
    response_class=Response,
    responses={
        200: {"content": {"audio/wav": {}}, "description": "The word, spoken."},
        304: {"description": "The caller already has this word."},
        404: {"description": "Not a word this account can be offered to hear."},
        503: {"description": "The voice is loading or unreachable."},
    },
)
async def get_spoken_word(
    word: str,
    if_none_match: str | None = Header(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Speak one word from the closed set. The caller must be allowed to hear it."""
    allowed = await speakable.word_to_speak(db, user, word)
    if allowed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no such word to hear"
        )

    tag = _etag(allowed)
    headers = {
        "ETag": tag,
        "Cache-Control": f"private, max-age={SPEAK_CACHE_SECONDS}",
    }

    # Checked before synthesising, not after: the whole point of a deterministic
    # rendering is that the answer is known without producing the audio again.
    if if_none_match is not None and tag in if_none_match:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    try:
        speech = await speak(
            allowed,
            noise_scale=PINNED_NOISE,
            noise_w_scale=PINNED_NOISE,
        )
    except TtsUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"the voice is not available: {exc}",
        ) from exc
    except TtsError as exc:
        # The word came from this system's own set, so a refusal or a malformed reply is
        # a disagreement between two of our services rather than anything the caller
        # did. 502 says that plainly instead of blaming the request.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"the voice could not say a word from the set: {exc}",
        ) from exc

    return Response(
        content=speech.audio,
        media_type="audio/wav",
        headers={**headers, "X-Duration-Ms": str(speech.duration_ms)},
    )
