#!/bin/sh
# Signs the app ad hoc, inside out, everything with the hardened runtime:
#   1. every Mach-O in Contents/Resources, found by its header: the libraries and extension
#      modules, then the executables (the interpreter, Postgres and its tools, the few the
#      environments carry) with library validation off;
#   2. Electron's own libraries, frameworks and helpers, and the fn helper; 3. the app itself.
# Ad hoc is a signature for this machine only: Gatekeeper refuses it anywhere else.
#   scripts/sign.sh [app]
. "$(dirname "$0")/lib.sh"

APP=${1:-$DESKTOP/dist/mac-arm64/SpeakLab.app}
ENT=$DESKTOP/build/entitlements
RES=$APP/Contents/Resources
FW=$APP/Contents/Frameworks
SIGN="codesign --force --sign - --timestamp=none --options runtime"

"$PYTHON" -I "$DESKTOP/scripts/macho.py" "$RES" > "$B/macho.txt"
TAB=$(printf '\t')
grep "^lib$TAB" "$B/macho.txt" | cut -f2- | tr '\n' '\0' | xargs -0 -n 200 $SIGN
grep "^exe$TAB" "$B/macho.txt" | cut -f2- | tr '\n' '\0' | xargs -0 -n 200 $SIGN --entitlements "$ENT/runtime.plist"
log "signed $(grep -c "^lib$TAB" "$B/macho.txt") libraries and $(grep -c "^exe$TAB" "$B/macho.txt") executables in Resources"

find "$FW" -type f \( -name '*.dylib' -o -name chrome_crashpad_handler -o -name ShipIt \) -print0 | xargs -0 $SIGN
for framework in "$FW"/*.framework; do $SIGN "$framework"; done
for helper in "$FW"/*.app; do $SIGN --entitlements "$ENT/electron.plist" "$helper"; done
# The fn helper links only the system's frameworks, so it needs no entitlement.
$SIGN --identifier local.speaklab.keys "$APP/Contents/MacOS/speaklab-keys"
$SIGN --entitlements "$ENT/electron.plist" "$APP"
log "signed Electron's frameworks and helpers, and the app"

codesign --verify --deep --strict "$APP"
log "codesign --verify --deep --strict: valid"
