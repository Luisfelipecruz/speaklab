#!/usr/bin/env bash
# The learner's side of the walkthrough, spoken by a synthetic voice.
#
#   ./piper.sh up      the learner's voice, beside the stack
#   ./voices.sh        writes voice/{turn1,turn2,reading,answer}.wav
#
# Beside out/ rather than inside it: the recorder empties out/ when a take starts.
#
# The voice is not the persona's. The stack's tts speaks for the persona, and a learner
# in the same voice would make the conversation impossible to follow by ear; this one is
# heard verbatim by the recogniser, every written mistake included.
#
# The lines are written for the take, with the mistakes and hesitations it is meant to
# show: a wrong tense, a malformed question, a comparative built the long way, a filler, a
# phrase said twice. The recorder's captions say the voice is synthetic, so nothing in the
# video is presented as a learner. It needs the stack up, because the reading is the
# passage as the API serves it.
set -euo pipefail
cd "$(dirname "$0")"
TTS="${TTS:-http://localhost:8104}"
API="${API:-http://localhost:8002}"
PASSAGE="${PASSAGE:-the-ship-and-the-sheep}"
OUT="${OUT:-voice}"
mkdir -p "$OUT"

say() {
  local name="$1" text="$2"
  python3 -c 'import json, sys; print(json.dumps({"text": sys.argv[1]}))' "$text" \
    | curl -sf -X POST "$TTS/synthesize" -H 'content-type: application/json' --data @- \
      -o "$OUT/$name.wav"
  echo "$OUT/$name.wav"
}

say turn1 "Hello. I see the advert for this flat yesterday, and I want to ask some questions. How much it cost every month?"
say turn2 "The last flat I visit was more cheap than this one, but it have not a balcony. Can you make the price lower if I am going to stay for two years?"
say reading "$(curl -sf "$API/passages/$PASSAGE" | python3 -c 'import json, sys; print(json.load(sys.stdin)["body"])')"
say answer "So, um, we delivered the feature two weeks late, and I want to, I want to explain why. First, the payment provider changed their system in the middle of the project. For example, the refund calls stopped working, and we had to rewrite them. Then our tests found two more problems, so we moved the date instead of shipping something broken. In short, the delay came from a change we did not control, and we chose a working release over the date."
