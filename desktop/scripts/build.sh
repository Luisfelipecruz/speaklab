#!/bin/sh
# make desktop: from the pinned downloads to a signed desktop/dist/mac-arm64/SpeakLab.app.
# Each step is its own script and can be run alone; this runs them in order.
. "$(dirname "$0")/lib.sh"
S=$DESKTOP/scripts

/bin/sh "$S/fetch.sh"
/bin/sh "$S/build-envs.sh"
/bin/sh "$S/build-web.sh"

log "the desktop package"
cd "$DESKTOP"
pnpm install --frozen-lockfile
pnpm exec install-electron

/bin/sh "$S/stage.sh"
/bin/sh "$S/package.sh"

APP=$DESKTOP/dist/mac-arm64/SpeakLab.app
if spctl --assess --type execute "$APP" 2> /dev/null; then
  echo "spctl accepts it, which an ad-hoc signature should not be"
else
  echo "spctl rejects it, as it does any ad-hoc signature: this build is for this Mac"
fi
log "built $APP"
