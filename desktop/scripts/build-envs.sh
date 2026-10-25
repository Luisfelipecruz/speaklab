#!/bin/sh
# One --target folder per service, against the bundled interpreter, from the pinned
# requirements and nothing published after build/versions.env's cutoff: wheels only, but
# for pron's one pure-Python sdist (distance), built with the setuptools pron itself pins.
# Then pip's own check per folder, as the images run it. The console scripts uv writes are
# removed: nothing runs them, and their first line names this machine's build folder.
#   scripts/build-envs.sh [service...]
. "$(dirname "$0")/lib.sh"

mkdir -p "$B/envs"
for svc in ${*:-api asr tts pron}; do
  req=$REPO/infra/$svc/requirements.txt
  out=$B/envs/$svc
  log "$svc, from infra/$svc/requirements.txt"
  rm -rf "$out"
  if [ "$svc" = pron ]; then
    grep -E '^setuptools==' "$req" > "$B/pron-build-constraints.txt"
    uv pip install --python "$PYTHON" --target "$out" --exclude-newer "$UV_EXCLUDE_NEWER" \
      --only-binary :all: --no-binary distance --build-constraints "$B/pron-build-constraints.txt" -r "$req"
  else
    uv pip install --python "$PYTHON" --target "$out" --exclude-newer "$UV_EXCLUDE_NEWER" --only-binary :all: -r "$req"
  fi
  PYTHONPATH=$out "$PYTHON" -m pip check
  rm -rf "$out/bin"
  du -sh "$out"
done
