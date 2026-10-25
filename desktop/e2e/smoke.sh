#!/bin/sh
# The host smoke test of the built app. A fresh data folder; the app launched with
# Chromium recording a file instead of the microphone; a person's path driven over the
# DevTools protocol (register, one conversation turn heard back, one read-aloud scored);
# then a quit, after which nothing of the app may still run.
#   desktop/e2e/smoke.sh [recording.wav] [models folder to clone]
# The recording defaults to the pronunciation suite's human reading (`make pron-fetch`).
# A models folder from an earlier launch saves the first launch's 1.75 GB download.
# Chromium's fake capture reads a file only with the audio service in the browser
# process, hence the last switch.
set -eu
E=$(cd "$(dirname "$0")" && pwd)
DESKTOP=$(cd "$E/.." && pwd)
REPO=$(cd "$DESKTOP/.." && pwd)
APP=$DESKTOP/dist/mac-arm64/SpeakLab.app
NODE=$DESKTOP/.build/tools/node/bin/node
WAV=${1:-$REPO/eval/golden/pron/voices-sp0307-sg0042.wav}
MODELS=${2:-}
PORT=9333

[ -x "$APP/Contents/MacOS/SpeakLab" ] || { echo "no app at $APP: make desktop first" >&2; exit 1; }
[ -f "$WAV" ] || { echo "no recording at $WAV: make pron-fetch, or name one" >&2; exit 1; }
running() { ps -axo command= | awk -v a="$APP/" 'index($0, a) == 1' | wc -l | tr -d ' '; }
[ "$(running)" = 0 ] || { echo "SpeakLab is already running; quit it first" >&2; exit 1; }

DATA=$(mktemp -d "${TMPDIR:-/tmp}/speaklab-smoke.XXXXXX")
if [ -n "$MODELS" ]; then cp -c -R "$MODELS" "$DATA/models"; fi
echo "{\"step\":\"data folder\",\"path\":\"$DATA\"}"

SPEAKLAB_DATA=$DATA "$APP/Contents/MacOS/SpeakLab" \
  --remote-debugging-port=$PORT --remote-debugging-address=127.0.0.1 \
  --use-fake-device-for-media-stream "--use-file-for-fake-audio-capture=$WAV%noloop" \
  --disable-features=AudioServiceOutOfProcess > "$DATA/app.out" 2>&1 &
app=$!

status=0
"$NODE" "$E/smoke.mjs" "$PORT" || status=$?

# Quit as Cmd+Q does, and wait for every process of the app to go.
kill -TERM "$app" 2> /dev/null || true
i=0
while [ "$(running)" != 0 ] && [ $i -lt 120 ]; do sleep 0.25; i=$((i + 1)); done
left=$(running)
echo "{\"step\":\"quit\",\"processes left\":$left}"
[ "$left" = 0 ] || status=1
echo "{\"step\":\"verdict\",\"pass\":$([ $status = 0 ] && echo true || echo false)}"
exit $status
