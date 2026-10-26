#!/bin/sh
# The fn helper, from native/keys.swift, with the Xcode this Mac has: one optimised arm64
# executable in .build/native, which electron-builder puts in Contents/MacOS and sign.sh
# signs with the rest of the app.
. "$(dirname "$0")/lib.sh"

log "the fn helper, native/keys.swift"
mkdir -p "$B/native"
/usr/bin/xcrun swiftc -O -target arm64-apple-macos14.0 -o "$B/native/speaklab-keys" "$DESKTOP/native/keys.swift"
ls -l "$B/native/speaklab-keys" | awk '{print $5 " bytes"}'
