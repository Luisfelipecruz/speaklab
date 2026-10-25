#!/bin/sh
# The frontend's standalone server, built as the image builds it, from a copy of the
# frontend's source files: nothing is installed into frontend/ itself. The browser's
# address for the API is compiled into the client bundle, so it is the app's own.
. "$(dirname "$0")/lib.sh"

src=$B/web-src
log "a copy of frontend/'s source files"
rm -rf "$src"
mkdir -p "$src"
source_files frontend | (cd "$REPO" && xargs -0 tar -cf -) | tar -xf - -C "$src" --strip-components 1

cd "$src"
log "pnpm install --frozen-lockfile"
pnpm install --frozen-lockfile
log "next build"
NEXT_PUBLIC_API_URL=http://127.0.0.1:8012 NODE_OPTIONS=--no-network-family-autoselection pnpm run build

# The image's runner stage: the traced server with its modules, and the static assets.
# Next roots its trace at the highest folder above the copy that holds a lockfile, which
# is desktop/, for the desktop package's own, and nests the server that deep inside
# .next/standalone. The server's folder must then be the whole of the output.
server=$(cd .next/standalone && find . -name server.js -not -path '*/node_modules/*' | head -1)
[ -n "$server" ] || { echo "next build wrote no server.js" >&2; exit 1; }
nested=${server%/server.js}
outside=$(cd .next/standalone && find . -type f -not -path "$nested/*" | wc -l | tr -d ' ')
[ "$outside" = 0 ] || { echo "$outside files of the standalone output lie outside $nested" >&2; exit 1; }
rm -rf "$B/web"
cp -R ".next/standalone/$nested" "$B/web"
cp -R .next/static "$B/web/.next/static"
du -sh "$B/web"
