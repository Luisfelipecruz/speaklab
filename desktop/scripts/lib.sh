# Sourced by every build script. Every download, tool and cache stays under desktop/.build,
# so removing that folder removes all of it, and nothing on the host's PATH (its uv, its
# Node, Homebrew) takes part: PATH is the build's own tools and the system's.
set -eu

DESKTOP=$(cd "$(dirname "$0")/.." && pwd)
REPO=$(cd "$DESKTOP/.." && pwd)
B=$DESKTOP/.build
TOOLS=$B/tools
DOWNLOADS=$B/downloads
STAGE=$B/stage
. "$DESKTOP/build/versions.env"

export UV_CACHE_DIR=$B/cache/uv UV_PYTHON_DOWNLOADS=never UV_NO_CONFIG=1
export PIP_CACHE_DIR=$B/cache/pip PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONNOUSERSITE=1
export npm_config_cache=$B/cache/npm npm_config_userconfig=$B/npmrc
export XDG_DATA_HOME=$B/xdg/data XDG_STATE_HOME=$B/xdg/state XDG_CONFIG_HOME=$B/xdg/config XDG_CACHE_HOME=$B/xdg/cache
export electron_config_cache=$B/cache/electron ELECTRON_CACHE=$B/cache/electron
export ELECTRON_BUILDER_CACHE=$B/cache/electron-builder
export NEXT_TELEMETRY_DISABLED=1 npm_config_update_notifier=false pnpm_config_update_notifier=false
export PATH="$TOOLS/node/bin:$TOOLS/pnpm:$TOOLS/uv:/usr/bin:/bin:/usr/sbin:/sbin"

PYTHON=$TOOLS/python/bin/python3.12

log() {
  printf '== %s\n' "$*"
}

get() { # url dest
  curl -fsSL --retry 5 --retry-all-errors --max-time 1800 -o "$2.part" "$1"
  mv "$2.part" "$2"
}

# verify algorithm pinned file [published]: the file hashes to the pinned value, and the
# value its publisher lists, when there is one, is the pinned value too.
verify() {
  if [ -n "${4:-}" ] && [ "$4" != "$2" ]; then
    echo "$3: its publisher lists $4, and build/versions.env pins $2" >&2
    exit 1
  fi
  printf '%s  %s\n' "$2" "$3" | shasum -a "$1" -c -
}

# A download is kept once it has passed its check, so a second build fetches nothing.
fresh() { # algorithm pinned file
  [ -f "$3" ] && printf '%s  %s\n' "$2" "$3" | shasum -a "$1" -c - > /dev/null 2>&1
}

# source_files path...: the files under those paths that git tracks or would track, NUL
# separated, from the working tree: a new file is in, an ignored one is not, and a tracked
# file deleted from the tree is left out.
source_files() {
  git -C "$REPO" ls-files -z --cached --others --exclude-standard -- "$@" |
    (cd "$REPO" && "$PYTHON" -I -c 'import os, sys; sys.stdout.write("".join(p + "\0" for p in sys.stdin.read().split("\0") if p and os.path.lexists(p)))')
}
