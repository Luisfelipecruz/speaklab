#!/bin/sh
# pnpm in desktop/, with the build's own Node and pnpm and every cache under .build.
. "$(dirname "$0")/lib.sh"
cd "$DESKTOP"
exec pnpm "$@"
