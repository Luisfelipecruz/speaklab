# The pronunciation service. Forced alignment and GOP, and nothing else.
#
# Build context is this directory, like asr and tts: nothing here needs anything from
# the rest of the tree, and editing a router in api/ must not invalidate a layer that
# takes ten minutes to rebuild.
#
# The layer order is deliberate and is the difference between a 20-second rebuild and a
# 12-minute one: torch, then the NLTK corpora, then the vocabulary, then the code. The
# code is what changes; it is last.
FROM python:3.12.14-slim-trixie

# The security fixes Debian has published since the base image was built, and no package
# added: the health check is a line of Python, and there is no ffmpeg — PyAV carries the
# ffmpeg libraries itself, the same trade infra/asr makes.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

# The same unprivileged account, with the same id, in every image that shares the
# model_cache volume, so a file one service downloads the others can read and replace.
# /models is created here and owned by that account, so a new volume mounted over it
# starts out writable.
RUN groupadd --system --gid 10001 speaklab \
    && useradd --system --uid 10001 --gid speaklab --create-home speaklab \
    && mkdir /models \
    && chown speaklab:speaklab /models

WORKDIR /app

# ── torch, from the CPU index, BEFORE everything else ───────────────────────
#
# This is not a micro-optimisation, it is 3.6 GB. PyPI's torch wheels declare the whole
# NVIDIA CUDA stack as dependencies **on linux/aarch64 as well as x86_64** — the aarch64
# wheels exist for Jetson and GH200 — so the obvious `pip install -r requirements.txt`
# on an Apple-silicon laptop produces an image carrying 2.9 GB of CUDA libraries and
# 652 MB of Triton that no code in it can ever execute. Measured, not assumed: the first
# build of this image came out at **8.51 GB**, and `du` inside it named the culprits.
#
# `--extra-index-url` does not fix it. Both indexes carry version 2.14.0 and pip is free
# to take either, which makes the image size depend on resolver mood. A separate install
# from an index that only *has* CPU builds is the version that cannot drift. The second
# install then finds torch already satisfied and pulls only the rest.
#
# Versions live in requirements.txt and are repeated here, which is the one duplication
# in this file. `pip check` at the end is what makes it safe: if the two ever disagree,
# the build fails rather than the image quietly carrying two torches.
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.14.0 torchaudio==2.11.0

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip check

# ── The two NLTK corpora g2p_en needs, at BUILD time ────────────────────────
#
# `averaged_perceptron_tagger_eng` for part-of-speech tagging and `cmudict` for the
# lexicon. m0 found this the hard way: g2p_en downloads them on first use, so a service
# that skips this step answers its first request only if it has internet, and answers it
# slowly. A container that fetches corpora on demand is a broken container.
ENV NLTK_DATA=/usr/share/nltk_data
RUN python -m nltk.downloader -d $NLTK_DATA averaged_perceptron_tagger_eng cmudict

# ── The phone vocabulary, vendored ──────────────────────────────────────────
#
# `vocab.json` is IN THE REPOSITORY, not downloaded here, and that is a deliberate
# change from what m0 prescribed. Three things follow from checking it in that do not
# follow from fetching it:
#
#   * **The phone map becomes testable without this image.** `api/tests/test_phone_map.py`
#     asserts the map against the model's real vocabulary in CI, on a runner with no
#     torch, no network and no 1.2 GB download. That test is the one that catches the
#     U+0261 trap, and a test that can only run inside a 2 GB image is a test that stops
#     being run.
#   * **The ids are pinned.** These 392 tokens are the meaning of every number this
#     service emits. Fetching them at build time means an upstream edit to the model card
#     silently redefines every phone in every stored score, with no diff anywhere.
#   * **The build stops needing the network** for anything but pip and NLTK.
#
# 4.6 KB. `app.py` still checks it against the loaded weights' own `vocab_size` at
# start-up, because a vendored file is a claim and the weights are the fact.
COPY vocab.json .

COPY phone_map.py g2p.py gop.py app.py ./

# The map asserts its whole table against that vocabulary at import and raises on any
# miss. Running it here means a wrong entry fails the BUILD — loudly, once, in front of
# whoever changed it — rather than at the first request in front of a user. A skipped
# phone is a pronunciation error that silently never gets scored.
RUN python -c "import phone_map; print(phone_map.summary())"

# Weights on the shared model_cache volume, never in the image: 1.2 GB that would have
# to be rebuilt to change model, and re-downloaded by every developer on every build.
ENV HF_HOME=/models

USER speaklab

EXPOSE 8103

# /health answers 200 with `model_loaded: false` while the weights download; the start
# period is for 1.2 GB of weights on a cold cache, not for the load.
HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=300s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8103/health', timeout=4)"]

# One worker. The model is loaded once per process, torch already uses every core it is
# given, and a second worker would double 1.2 GB of resident weights to halve the
# threads available to each.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8103"]
