#!/usr/bin/env bash
# The two voices the walkthrough needs beyond the persona's: the learner and the narrator.
#
#   ./piper.sh up      start both, and wait until each has its voice loaded
#   ./piper.sh down    stop both
#
# Each is the stack's own tts image running a different Piper voice, on a port of its own
# and with a volume of its own, so the running stack and its model cache are untouched.
# The first `up` downloads each voice once, about 60 and 110 MB.
#
#   learner    en_GB-alba-medium   :8104   heard verbatim by the recogniser, mistakes and all
#   narrator   en_US-ryan-high     :8113
#
# Three different voices, because the persona speaks with the stack's voice: a learner who
# sounded like the persona would make the conversation impossible to follow by ear.
set -euo pipefail
IMAGE="${IMAGE:-speaklab-tts:latest}"
VOLUME="${VOLUME:-speaklab-demo-voices}"
VOICES=(
  "learner en_GB-alba-medium 8104"
  "narrator en_US-ryan-high 8113"
)

up() {
  for spec in "${VOICES[@]}"; do
    set -- $spec
    if [ -n "$(docker ps -q --filter "name=^sl-voice-$1$")" ]; then
      echo "$1: already running on :$3"
    else
      docker run -d --rm --name "sl-voice-$1" -p "$3:8102" \
        -e PIPER_VOICE="$2" -e PIPER_VOICE_DIR=/models/piper \
        -v "$VOLUME":/models "$IMAGE" >/dev/null
      echo "$1: started $2 on :$3"
    fi
  done
  for spec in "${VOICES[@]}"; do
    set -- $spec
    for _ in $(seq 1 90); do
      if curl -sf "localhost:$3/health" | grep -q '"voice_loaded":true'; then
        echo "$1: $2 loaded"
        continue 2
      fi
      sleep 2
    done
    echo "$1: $2 did not load in 180 s; docker logs sl-voice-$1" >&2
    exit 1
  done
}

down() {
  for spec in "${VOICES[@]}"; do
    set -- $spec
    docker stop "sl-voice-$1" >/dev/null 2>&1 && echo "$1: stopped" || echo "$1: not running"
  done
}

case "${1:-}" in
  up) up ;;
  down) down ;;
  *) echo "usage: $0 up|down" >&2; exit 2 ;;
esac
