#!/bin/sh
# The app's icon, from build/icon.svg: every size rendered by the app's own Electron,
# offscreen, then packed by the system's iconutil into .build/icon.icns. Only the SVG is
# tracked.
. "$(dirname "$0")/lib.sh"

log "the icon"
rm -rf "$B/icon.iconset" "$B/icon-profile"
# macOS keeps Electron's defaults under its bundle id in ~/Library/Preferences, and cannot be
# told to keep them anywhere else: the file goes again unless it was there before.
prefs=$HOME/Library/Preferences/com.github.Electron.plist
kept=0
[ ! -e "$prefs" ] || kept=1
status=0
"$DESKTOP/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron" \
  "$DESKTOP/scripts/render-icon.mjs" "$DESKTOP/build/icon.svg" "$B/icon.iconset" > "$B/icon.log" 2>&1 || status=$?
if [ "$kept" = 0 ]; then
  defaults delete com.github.Electron 2> /dev/null || true
  rm -f "$prefs"
fi
[ "$status" = 0 ] || { echo "the icon's Electron exited with $status; see $B/icon.log" >&2; exit 1; }
count=$(ls "$B/icon.iconset" 2>/dev/null | wc -l | tr -d ' ')
[ "$count" = 10 ] || { echo "the icon rendered $count of 10 sizes; see $B/icon.log" >&2; exit 1; }
iconutil -c icns -o "$B/icon.icns" "$B/icon.iconset"
ls -l "$B/icon.icns" | awk '{ print $5 " bytes" }'
