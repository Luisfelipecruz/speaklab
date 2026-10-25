#!/bin/sh
# Downloads every prebuilt piece into .build/downloads, checks each one, and unpacks the
# tools into .build/tools. A piece already downloaded and checked is not downloaded again.
. "$(dirname "$0")/lib.sh"

mkdir -p "$DOWNLOADS" "$TOOLS"
cd "$DOWNLOADS"

# unpack archive folder [strip]: a fresh copy of the archive in .build/tools/<folder>,
# skipped when the copy there came from this same archive.
unpack() {
  if [ "$(cat "$TOOLS/$2/.from" 2>/dev/null)" = "$1" ]; then return; fi
  rm -rf "$TOOLS/$2"
  mkdir -p "$TOOLS/$2"
  tar -xzf "$1" -C "$TOOLS/$2" --strip-components "${3:-1}"
  printf '%s\n' "$1" > "$TOOLS/$2/.from"
}

log "Node $NODE_VERSION"
if ! fresh 256 "$NODE_SHA256" "$NODE_FILE"; then
  get "https://nodejs.org/dist/v${NODE_VERSION}/${NODE_FILE}" "$NODE_FILE"
fi
get "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt" node-SHASUMS256.txt
verify 256 "$NODE_SHA256" "$NODE_FILE" "$(awk -v f="$NODE_FILE" '$2 == f { print $1 }' node-SHASUMS256.txt)"
unpack "$NODE_FILE" node

log "pnpm $PNPM_VERSION"
if ! fresh 512 "$PNPM_SHA512" "$PNPM_FILE"; then
  get "https://registry.npmjs.org/@pnpm/exe.darwin-arm64/-/${PNPM_FILE}" "$PNPM_FILE"
fi
get "https://registry.npmjs.org/@pnpm%2Fexe.darwin-arm64/${PNPM_VERSION}" pnpm-registry.json
integrity=$("$TOOLS/node/bin/node" -e 'process.stdout.write(JSON.parse(require("fs").readFileSync(0)).dist.integrity)' < pnpm-registry.json)
verify 512 "$PNPM_SHA512" "$PNPM_FILE" "$(printf %s "${integrity#sha512-}" | base64 -D | xxd -p | tr -d '\n')"
unpack "$PNPM_FILE" pnpm
found=$("$TOOLS/pnpm/pnpm" --version)
[ "$found" = "$PNPM_VERSION" ] || { echo "pnpm reports $found, not $PNPM_VERSION" >&2; exit 1; }

log "uv $UV_VERSION"
UV_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}"
if ! fresh 256 "$UV_SHA256" "$UV_FILE"; then
  get "${UV_URL}/${UV_FILE}" "$UV_FILE"
fi
get "${UV_URL}/${UV_FILE}.sha256" uv.sha256
verify 256 "$UV_SHA256" "$UV_FILE" "$(awk '{ print $1; exit }' uv.sha256)"
unpack "$UV_FILE" uv

log "CPython $PYTHON_VERSION ($PBS_TAG)"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}"
if ! fresh 256 "$PYTHON_SHA256" "$PYTHON_FILE"; then
  # The checksum file names the file with a literal '+', which the URL escapes.
  get "${PBS_URL}/$(printf %s "$PYTHON_FILE" | sed 's/+/%2B/')" "$PYTHON_FILE"
fi
get "${PBS_URL}/SHA256SUMS" python-SHA256SUMS
verify 256 "$PYTHON_SHA256" "$PYTHON_FILE" "$(awk -v f="$PYTHON_FILE" '$2 == f { print $1 }' python-SHA256SUMS)"
unpack "$PYTHON_FILE" python
found=$("$PYTHON" -c 'import platform; print(platform.python_version())')
[ "$found" = "$PYTHON_VERSION" ] || { echo "the interpreter reports $found, not $PYTHON_VERSION" >&2; exit 1; }

log "PostgreSQL $PG_VERSION"
PG_URL="https://github.com/theseus-rs/postgresql-binaries/releases/download/${PG_VERSION}"
if ! fresh 256 "$PG_SHA256" "$PG_FILE"; then
  get "${PG_URL}/${PG_FILE}" "$PG_FILE"
fi
get "${PG_URL}/${PG_FILE}.sha256" pg.sha256
verify 256 "$PG_SHA256" "$PG_FILE" "$(awk '{ print $1; exit }' pg.sha256)"
unpack "$PG_FILE" pg

log "the voice, $VOICE"
mkdir -p voice
VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/${VOICE_REVISION}/${VOICE_PATH}"
fresh 256 "$VOICE_ONNX_SHA256" "voice/${VOICE}.onnx" || get "${VOICE_URL}/${VOICE}.onnx" "voice/${VOICE}.onnx"
fresh 256 "$VOICE_JSON_SHA256" "voice/${VOICE}.onnx.json" || get "${VOICE_URL}/${VOICE}.onnx.json" "voice/${VOICE}.onnx.json"
verify 256 "$VOICE_ONNX_SHA256" "voice/${VOICE}.onnx"
verify 256 "$VOICE_JSON_SHA256" "voice/${VOICE}.onnx.json"

log "the NLTK corpora"
mkdir -p nltk
NLTK_URL="https://raw.githubusercontent.com/nltk/nltk_data/${NLTK_REVISION}/packages"
fresh 256 "$NLTK_CMUDICT_SHA256" nltk/cmudict.zip || get "${NLTK_URL}/corpora/cmudict.zip" nltk/cmudict.zip
fresh 256 "$NLTK_TAGGER_SHA256" nltk/averaged_perceptron_tagger_eng.zip ||
  get "${NLTK_URL}/taggers/averaged_perceptron_tagger_eng.zip" nltk/averaged_perceptron_tagger_eng.zip
verify 256 "$NLTK_CMUDICT_SHA256" nltk/cmudict.zip
verify 256 "$NLTK_TAGGER_SHA256" nltk/averaged_perceptron_tagger_eng.zip

log "fetched"
du -sh "$DOWNLOADS" "$TOOLS"
