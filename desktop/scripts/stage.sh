#!/bin/sh
# Everything Contents/Resources gets, assembled in .build/stage, with the services' code
# from the source files, bytecode compiled into every Python tree (nothing is written
# inside the signed bundle at run time, so a missing .pyc would be compiled again on every
# start), and a checksum of every file and link in stage.sha256.
. "$(dirname "$0")/lib.sh"

rm -rf "$STAGE"
mkdir -p "$STAGE"

log "the interpreter"
cp -R "$TOOLS/python" "$STAGE/python"
rm -f "$STAGE/python/.from"

log "the environments"
mkdir -p "$STAGE/envs"
for svc in api asr tts pron; do cp -R "$B/envs/$svc" "$STAGE/envs/$svc"; done

log "the services' code: api/ without its tests, the model services without their Dockerfiles"
mkdir -p "$STAGE/src"
source_files api infra/asr infra/tts infra/pron |
  tr '\0' '\n' | grep -v -e '^api/tests/' -e '/Dockerfile$' | tr '\n' '\0' |
  (cd "$REPO" && xargs -0 tar -cf -) | tar -xf - -C "$STAGE/src"

log "PostgreSQL, without its headers and build files"
cp -R "$TOOLS/pg" "$STAGE/pg"
rm -rf "$STAGE/pg/include" "$STAGE/pg/lib/pgxs" "$STAGE/pg/.from"

log "the voice"
mkdir -p "$STAGE/voices"
cp "$DOWNLOADS/voice/${VOICE}.onnx" "$DOWNLOADS/voice/${VOICE}.onnx.json" "$STAGE/voices/"

log "the NLTK corpora, as the pron image holds them: each zip and its contents"
mkdir -p "$STAGE/nltk_data/corpora" "$STAGE/nltk_data/taggers"
cp "$DOWNLOADS/nltk/cmudict.zip" "$STAGE/nltk_data/corpora/"
cp "$DOWNLOADS/nltk/averaged_perceptron_tagger_eng.zip" "$STAGE/nltk_data/taggers/"
unzip -q "$STAGE/nltk_data/corpora/cmudict.zip" -d "$STAGE/nltk_data/corpora"
unzip -q "$STAGE/nltk_data/taggers/averaged_perceptron_tagger_eng.zip" -d "$STAGE/nltk_data/taggers"

log "the window's server"
cp -R "$B/web" "$STAGE/web"

log "bytecode, unchecked-hash: a file that does not compile fails the build"
"$PYTHON" -I -m compileall -q -j 0 --invalidation-mode unchecked-hash \
  "$STAGE/python/lib/python3.12" "$STAGE/envs" "$STAGE/src"

log "stage.sha256"
"$PYTHON" -I "$DESKTOP/scripts/tree-sums.py" "$STAGE" > "$B/stage.sha256"
wc -l < "$B/stage.sha256" | tr -d ' ' | sed 's/$/ entries/'
du -sh "$STAGE"/*
