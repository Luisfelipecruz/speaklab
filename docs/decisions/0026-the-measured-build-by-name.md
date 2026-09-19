# 0026 — The model by its measured build, and a stack that reports what is running

Status: accepted · supersedes §2 of [0025](0025-gemma-4-with-thinking-off.md)

The conversation and analysis model is configured as `gemma4:e4b`, the named build every
published figure was measured on, and the stack reports the build it is actually talking
to — its digest, size and quantisation — and says so when that build is not the measured
one. This records why a tag with a size in it replaces `latest`, what the readiness probe
now tells, and what the frontend's own healthcheck had wrong.

## What was decided

1. **The default model is `gemma4:e4b`, never `latest`.** Ollama's `gemma4` family carries
   five builds under one name — e2b, e4b, 12b, 26b and 31b — and `latest` is a pointer
   that moves when the library does. A machine that has pulled keeps its build until it
   pulls again, so nothing stops working; but a fresh clone pulling `latest` could run a
   model of another size under a README, a report and a cover that describe the 8.0B
   build. The named tag whose manifest is byte for byte the local `gemma4:latest` is
   `e4b`, found by hashing the library's manifests without pulling anything. It is the
   default in `api/config.py`, `docker-compose.yml`, `.env.example`, the `Makefile`, the
   Quick start, CONTRIBUTING and the PRD's model table, and a test refuses a default that
   ends in `latest`.
2. **The probe reports the build, not just the name.** `/api/tags` already carries each
   model's manifest digest, size and quantisation, so `GET /health/models` returns them
   beside the model's name, `make llm-check` prints them, and the evaluation report's
   first line names the build the figures describe. A tag is a pointer; a digest is a
   build.
3. **A different build is `degraded`, not `ok` and not `error`.** The measured digest is
   in the configuration beside the measured model, and it is expected only when the
   measured model is configured (`OLLAMA_MODEL_DIGEST` overrides it, and empties it for a
   model with no measured build). A pulled build with another digest answers, so
   `ready` stays true and conversations work; `/health` says `degraded`, `make llm-check`
   exits non-zero and names both builds and the pull command — and says that if the build
   stays after a pull, the library has moved on and the figures are due a new measurement.
4. **An Ollama too old for the model is named before the pull fails.** The probe asks
   `/api/version` beside `/api/tags`. When the model is missing and the version is older
   than the model's requirement (`OLLAMA_MIN_VERSION`, 0.20.0 for this build), the detail
   says which version is needed and where to get it, instead of a pull command that fails
   with a message about the file format.
5. **The frontend's healthcheck fetches `127.0.0.1:3000`.** In the image `localhost`
   resolves to `::1` first; busybox `wget` tries that one address and stops, and Next
   listens on IPv4 only, so the container served every request while Compose reported it
   unhealthy. The Python healthchecks of the other four images try every address a name
   resolves to and were never wrong. A test over the Dockerfiles keeps `wget` on a
   numeric address.

## Measured

- The library's manifests for the six `gemma4` tags, fetched and hashed: `e4b` and
  `latest` both `c6eb396dbd59…`; e2b `7fbdbf8f5e45…`, 12b `4eb23ef187e2…`, 26b
  `08ae7ec1744b…`, 31b `6316f0629137…`. The local `gemma4:latest` manifest hashes to
  the same `c6eb396dbd59…`; Ollama lists it as 8.0B, Q4_K_M, 9 608 350 718 bytes,
  requiring 0.20.0, on Ollama 0.34.2.
- `speaklab-frontend-1` reported `unhealthy` for an hour while answering every request;
  its healthcheck log read `wget: can't connect to remote host: Connection refused`.
  With the numeric address the container reports `healthy` within its start period.

## Costs

- **Two calls a probe instead of one.** `/api/version` beside `/api/tags`, every ten
  seconds, both reading local state and loading no weights.
- **A pinned tag has to be re-measured to move.** When the library ships a new `e4b`
  build, a fresh clone's `make llm-check` will refuse it until a measurement accepts the
  new digest into the configuration. That is the point.

## Revisit if

- Ollama's library publishes digests in a form the probe could compare with the tag
  itself, so the pin could name a digest instead of a tag.
- A second model is measured and shipped as an alternative: the configuration then
  carries a table of measured builds, not one.
