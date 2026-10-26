#!/bin/sh
# Say it in English on the built app, timed: dictations into TextEdit with the model warm,
# then the first after Ollama has unloaded it, and after each the app in front checked and
# the clipboard read. A fresh data folder; the app launched with Chromium recording a clip
# instead of the microphone, with the key played through a pipe in place of its helper,
# and with its trace on; then a quit, after which nothing of the app may still run.
#   desktop/e2e/say.sh <clip.webm|clip.wav> [models folder to clone] [dictations]
# A golden clip is WebM, and Chromium's fake capture reads WAV, so a WebM clip is turned
# into one first, in the asr image. TextEdit is brought forward with `open`, which asks for
# no permission; FULL=1 puts its window in full screen first, which needs Accessibility for
# the terminal running this. The harness writes to the clipboard.
set -eu
E=$(cd "$(dirname "$0")" && pwd)
DESKTOP=$(cd "$E/.." && pwd)
REPO=$(cd "$DESKTOP/.." && pwd)
APP=$DESKTOP/dist/mac-arm64/SpeakLab.app
NODE=$DESKTOP/.build/tools/node/bin/node
CLIP=${1:?usage: desktop/e2e/say.sh <clip.webm|clip.wav> [models folder] [dictations]}
MODELS=${2:-}
COUNT=${3:-20}
PORT=9334

[ -x "$APP/Contents/MacOS/SpeakLab" ] || { echo "no app at $APP: make desktop first" >&2; exit 1; }
[ -f "$CLIP" ] || { echo "no clip at $CLIP" >&2; exit 1; }
running() { ps -axo command= | awk -v a="$APP/" 'index($0, a) == 1' | wc -l | tr -d ' '; }
[ "$(running)" = 0 ] || { echo "SpeakLab is already running; quit it first" >&2; exit 1; }

DATA=$(mktemp -d "${TMPDIR:-/tmp}/speaklab-say.XXXXXX")
if [ -n "$MODELS" ]; then cp -c -R "$MODELS" "$DATA/models"; fi
echo "{\"step\":\"data folder\",\"path\":\"$DATA\"}"

case "$CLIP" in
  *.wav) WAV=$CLIP ;;
  *)
    WAV=$DATA/clip.wav
    cp "$CLIP" "$DATA/clip.in"
    docker compose -f "$REPO/docker-compose.yml" run --rm --no-deps -T -v "$DATA:/clip" \
      --entrypoint python asr - <<'EOF'
import wave

import av
import numpy as np

with av.open("/clip/clip.in") as container:
    resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)
    chunks = []
    for frame in container.decode(audio=0):
        chunks += [out.to_ndarray().reshape(-1) for out in resampler.resample(frame)]
    chunks += [out.to_ndarray().reshape(-1) for out in resampler.resample(None)]
pcm = np.concatenate(chunks).astype("<i2")
with wave.open("/clip/clip.wav", "wb") as out:
    out.setnchannels(1)
    out.setsampwidth(2)
    out.setframerate(48000)
    out.writeframes(pcm.tobytes())
print(f'{{"step":"clip","seconds":{len(pcm) / 48000:.2f}}}')
EOF
    ;;
esac
SECONDS_LONG=$(/usr/bin/afinfo "$WAV" | awk '/estimated duration/ {print $3}')

KEYS=$DATA/keys.pipe
mkfifo "$KEYS"
SPEAKLAB_DATA=$DATA SPEAKLAB_SAY_KEYS=$KEYS SPEAKLAB_SAY_TRACE=$DATA/say-trace.jsonl \
  "$APP/Contents/MacOS/SpeakLab" \
  --remote-debugging-port=$PORT --remote-debugging-address=127.0.0.1 \
  --use-fake-device-for-media-stream "--use-file-for-fake-audio-capture=$WAV%noloop" \
  --disable-features=AudioServiceOutOfProcess > "$DATA/app.out" 2>&1 &
app=$!

status=0
FULL=${FULL:-0} "$NODE" "$E/say.mjs" "$PORT" "$KEYS" "$DATA/say-trace.jsonl" "$SECONDS_LONG" "$COUNT" || status=$?

# Quit as Cmd+Q does, and wait for every process of the app to go.
kill -TERM "$app" 2> /dev/null || true
i=0
while [ "$(running)" != 0 ] && [ $i -lt 120 ]; do sleep 0.25; i=$((i + 1)); done
left=$(running)
echo "{\"step\":\"quit\",\"processes left\":$left}"
[ "$left" = 0 ] || status=1
echo "{\"step\":\"verdict\",\"pass\":$([ $status = 0 ] && echo true || echo false)}"
exit $status
