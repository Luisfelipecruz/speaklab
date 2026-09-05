# SpeakLab — every operation worth having a name.
#
# Five services run by default as of m5: postgres, api, frontend, asr and tts. Only the
# pronunciation service is still behind a profile, because a profiled service is excluded
# from `up` AND from `build`, which is what lets docker-compose.yml declare the infra/pron
# build context that m8 has not created yet.

.PHONY: help up down restart logs ps health test test-frontend lint fmt fmt-eval clean \
        pron-up llm-up migrate migrate-down migrate-status seed eval eval-local asr-wer \
        tts-latency tts-sample turn-latency turn-latency-noflow pron-golden pron-fetch \
        persona-adherence corpus analyze analyze-dry error-precision rollup rollup-dry \
        rollup-force

help:                              ## This list
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ── Everyday ────────────────────────────────────────────────────────────────

up:                                ## Start the whole default stack (5 services)
	docker compose up -d

down:                              ## Stop everything. Volumes survive.
	docker compose down

restart:                           ## Recreate the api container (after a dependency change)
	docker compose up -d --build api

logs:                              ## Tail all logs
	docker compose logs -f

ps:                                ## What is running, and is it healthy
	docker compose ps

health:                            ## The API's own account of what is degraded
	@curl -s http://localhost:8002/health | python3 -m json.tool

# ── Quality ─────────────────────────────────────────────────────────────────

test:                              ## Run the API suite in a container
	docker compose --profile tools run --rm test

# The frontend's suite is a separate target rather than part of `test`, for the same
# reason CI runs them as two jobs: they share no fixtures, they fail for unrelated
# reasons, and the API loop is the one that gets run every few minutes. `--no-deps` so
# it does not wait for a healthy api to run assertions that never leave the browser.
test-frontend:                     ## Run the frontend suite (Jest + RTL) in a container
	docker compose run --rm --no-deps frontend npm test

# `--exclude eval` on both, and the reason is structural rather than stylistic. Inside
# the container /app is api/, and eval/ is mounted into it READ-ONLY so that the corpus a
# system is evaluated on cannot be rewritten by the system being evaluated.
# A formatter pointed at /app therefore tries to write to a read-only mount and fails.
# CI lints `api` from the repository root, where eval/ is a sibling and never in scope —
# so this exclusion makes the two agree rather than letting them differ silently.
# The two exclusions are NOT the same pattern, and that difference is load-bearing.
# ruff's `--exclude` matches path components, so `eval` means the directory. black's is a
# regular expression `re.search`ed against the whole path, so a bare `eval` also matches
# tests/eval_out.py and tests/test_eval_harness.py. It did: black checked 99 files where
# it should have checked 105, and six files with "eval" in their names were formatted by
# nothing for as long as they existed. Anchored, it means the directory and only that.
#
# m11 put real code in eval/ — a runner, a report generator and the arithmetic they share
# — so the directory is checked in its own pass rather than skipped. It cannot be checked
# in the same pass as /app: it is mounted read-only, and `--fix` would try to write to it.
lint:                              ## ruff + black, check only
	docker compose --profile tools run --rm --entrypoint sh test -c \
		"ruff check --exclude eval /app && black --check --exclude '^/eval/' /app \
		 && ruff check /app/eval && black --check /app/eval"

fmt:                               ## ruff --fix + black, in place
	docker compose --profile tools run --rm --entrypoint sh test -c \
		"ruff check --fix --exclude eval /app && black --exclude '^/eval/' /app"

# Separate from `fmt`, and it takes its own writable mount at a different path rather
# than making /app/eval writable. Formatting is a thing a developer does to source; it is
# not a thing any measurement can do to the corpus it is graded on, and keeping the two
# capabilities in different commands is what keeps that true.
fmt-eval:                          ## ruff --fix + black over eval/, via a writable mount
	docker compose --profile tools run --rm -v "$$PWD/eval:/eval-rw" \
		--entrypoint sh test -c "ruff check --fix /eval-rw && black /eval-rw"

# ── Model services ──────────────────────────────────────────────────────────

pron-up:                           ## Start the pronunciation service (m8). 1.78 GB.
	@echo "Not in the default stack: this is the only image with torch in it, and the"
	@echo "stack has to stay usable by somebody who never wants to download it (D10)."
	@echo "First start also pulls 1.2 GB of wav2vec2 weights onto the model_cache"
	@echo "volume — measured at 109 s including the download, 2 s once cached."
	docker compose --profile pron up -d

pron-fetch:                        ## Download the pronunciation probe recording
	@echo "eval/golden/pron holds no audio in git (*.wav is ignored), so this"
	@echo "is how the probe gets onto a machine rather than an audit step."
	python3 eval/golden/pron/fetch.py

llm-up:                            ## Start the CONTAINERISED LLM. On macOS you do not want this.
	@echo "Docker Desktop on macOS cannot pass the Apple GPU into a Linux container, so"
	@echo "this runs on CPU while the host's Ollama uses Metal. The default"
	@echo "OLLAMA_BASE_URL already points at the host (host.docker.internal:11434)."
	@echo "This target is for a Linux host with a GPU, or for CI. Ctrl-C to stop."
	docker compose --profile llm up -d ollama
	docker compose --profile llm exec ollama ollama pull $${OLLAMA_MODEL:-gemma3:4b}

# ── Data ────────────────────────────────────────────────────────────────────

migrate:                           ## Apply Alembic migrations to the running stack
	docker compose exec api alembic upgrade head

migrate-down:                      ## Roll back one revision. Read the downgrade first.
	docker compose exec api alembic downgrade -1

migrate-status:                    ## Which revision the database is on, and what exists
	@docker compose exec api alembic current
	@docker compose exec api alembic history

seed:                              ## Load the 8 scenarios and 12 passages. Idempotent.
	docker compose exec api python -m scripts.seed

asr-wer:                           ## Measure WER on the golden set against the live asr
	@echo "Ten LibriSpeech utterances through the running recogniser. Needs \`make up\`."
	docker compose --profile tools run --rm \
		-e ASR_URL=http://asr:8101 test \
		python -m pytest /app/tests/test_asr_golden.py -v -s

tts-latency:                       ## Measure synthesis latency against the live tts
	@echo "Whole-reply and per-sentence synthesis through the running voice. Needs \`make up\`."
	docker compose --profile tools run --rm \
		-e TTS_URL=http://tts:8102 test \
		python -m pytest /app/tests/test_tts_live.py -v -s

tts-sample:                        ## Synthesise a WAV you can actually listen to
	@echo "Voice quality is a judgement no assertion makes for you. This writes a file;"
	@echo "play it. spike/ is gitignored, so the audio cannot reach a commit."
	@mkdir -p spike/tts-sample
	@curl -sf -X POST http://localhost:8102/synthesize \
		-H 'content-type: application/json' \
		-d '{"text":"That sounds like a reasonable plan, though I would want to confirm the delivery date before we commit to anything. Could you check with your supplier and let me know by Friday?"}' \
		-o spike/tts-sample/reply.wav \
		&& echo "wrote spike/tts-sample/reply.wav" \
		|| echo "no answer from http://localhost:8102 — is the stack up?"

turn-latency:                      ## Measure a whole conversational turn, end to end
	@echo "Twenty turns through the real recogniser, the real model and the real voice."
	@echo "Needs \`make up\` and Ollama running on the host. Takes a couple of minutes."
	docker compose --profile tools run --rm \
		-e ASR_URL=http://asr:8101 \
		-e TTS_URL=http://tts:8102 \
		-e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
		test python -m pytest /app/tests/test_conversation_live.py -v -s

turn-latency-noflow:               ## The same measurement with PRD 9.1's first fallback OFF
	@echo "Generation and synthesis in series rather than overlapped. This is the control"
	@echo "arm for the comparison in docs/decisions/0003."
	docker compose --profile tools run --rm \
		-e ASR_URL=http://asr:8101 \
		-e TTS_URL=http://tts:8102 \
		-e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
		-e LLM_STREAM_TO_TTS=0 \
		test python -m pytest /app/tests/test_conversation_live.py -v -s -k whole_turn

analyze:                           ## Analyse the user turns nothing has analysed yet
	@echo "Grammar, fluency and error labelling over every outstanding turn. Needs"
	@echo "\`make up\` and Ollama on the host. About a second and a half per turn."
	docker compose exec api python -m scripts.analyze_backfill --all

analyze-dry:                       ## List what analysis is outstanding, and stop
	docker compose exec api python -m scripts.analyze_backfill --dry-run

error-precision:                   ## Score error detection against the hand-labelled set
	@echo "Seven real turns, labelled by reading them before any detector existed."
	@echo "Prints precision and recall; asserts only that the machinery holds, because"
	@echo "a figure over this few proposals says more about the sample than the model."
	@echo "Rebuild the set first if the corpus has grown:"
	@echo "  docker compose exec api python /app/eval/golden/errors/build.py"
	docker compose --profile tools run --rm \
		-e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
		test python -m pytest /app/tests/test_error_precision.py -v -s

rollup:                            ## Rebuild the progress snapshots every account is owed
	@echo "Collapses analysed turns and scored readings into one row per period. Ending"
	@echo "a session already does this, so on a working stack it usually has nothing to"
	@echo "do — it is here for read-aloud scoring and for turns filled in by a backfill."
	docker compose exec api python -m scripts.rollup

rollup-dry:                        ## Say which accounts are out of date, and stop
	docker compose exec api python -m scripts.rollup --dry-run

rollup-force:                      ## Recompute every snapshot, not only the stale ones
	@echo "For after a change to the rollup arithmetic, when every stored snapshot is a"
	@echo "number produced by code that no longer exists. Otherwise use \`make rollup\`."
	docker compose exec api python -m scripts.rollup --force

pron-golden:                       ## Measure GOP against the live pron service
	@echo "The m0 experiment, re-run through the real service: real human speech scored"
	@echo "against text containing phones the speaker did not produce. Gate is 8 of 10."
	@echo "Needs \`make pron-up\` and \`make pron-fetch\`. Takes about two and a half minutes."
	docker compose --profile tools run --rm \
		-e PRON_URL=http://pron:8103 test \
		python -m pytest /app/tests/test_gop.py -v -s

persona-adherence:                 ## Score persona adherence, and score the judge too
	@echo "Six probes through the real model, five deterministic guardrails, and an LLM"
	@echo "judge that is itself measured against ten hand-labelled replies on every run."
	@echo "Needs Ollama on the host. About two minutes."
	docker compose --profile tools run --rm \
		-e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
		test python -m pytest /app/tests/test_persona_adherence.py -v -s

corpus:                            ## How much practice this system has actually seen
	@echo "A query, not a measurement. Every undecidable verdict in docs/evaluation.md"
	@echo "traces back to these counts."
	docker compose exec api python -m scripts.corpus

eval:                              ## Every suite that can run, then docs/evaluation.md
	@echo "Runs the four measurement suites and the corpus census, then writes"
	@echo "docs/evaluation.md from what they produced. A suite whose service is not up"
	@echo "SKIPS and is reported as not run — never as passing, and never with a figure"
	@echo "carried forward from a previous run."
	@echo ""
	@echo "For everything to run you need: \`make up\`, \`make pron-up\`, and Ollama on"
	@echo "the host with the configured model pulled. Takes about five minutes."
	python3 eval/run.py

eval-local:                        ## The same harness without Docker. What CI runs.
	@echo "Runs the suites in this environment rather than in a container, and writes to"
	@echo "a scratch path. Everything model-facing skips unless you have services up and"
	@echo "the URLs exported — which is the point: it proves the harness works with no"
	@echo "model layer at all."
	python3 eval/run.py --local --out /tmp/speaklab-evaluation.md

# ── Destructive ─────────────────────────────────────────────────────────────

clean:                             ## Stop everything and WIPE the database and every
                                   ## downloaded model. Correct after a schema change on
                                   ## an empty project; destructive at any other time.
	docker compose down -v --remove-orphans
