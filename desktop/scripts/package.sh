#!/bin/sh
# The app from what is already staged: the main process compiled, the icon rendered,
# electron-builder, the bundle checked against the stage, and signed. build.sh runs this
# after the stage.
. "$(dirname "$0")/lib.sh"
S=$DESKTOP/scripts
cd "$DESKTOP"

log "the main process"
rm -rf out
pnpm exec tsc -p tsconfig.json

/bin/sh "$S/icon.sh"

log "electron-builder"
rm -rf dist
pnpm exec electron-builder --config build/electron-builder.yml --mac dir --arm64
APP=$DESKTOP/dist/mac-arm64/SpeakLab.app
# Electron's own demo app, which comes with the distribution; app.asar is the app.
rm -f "$APP/Contents/Resources/default_app.asar"

log "the bundle holds the stage, file for file and link for link"
"$PYTHON" -I "$S/tree-sums.py" "$APP/Contents/Resources" python envs src pg voices nltk_data web > "$B/bundle.sha256"
if ! cmp -s "$B/stage.sha256" "$B/bundle.sha256"; then
  diff "$B/stage.sha256" "$B/bundle.sha256" | head -20
  echo "the bundle's Resources differ from .build/stage" >&2
  exit 1
fi
echo "$(wc -l < "$B/stage.sha256" | tr -d ' ') entries, the same"

/bin/sh "$S/sign.sh" "$APP"
du -sh "$APP"
