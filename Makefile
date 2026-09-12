# SpeakLab. `make help` lists every target.
#
# The default stack is five services: postgres, api, frontend, asr and tts. pron is behind
# a profile because it is the only image with torch in it. The conversation model is
# Ollama on the host, not a service here.

.PHONY: help setup up down restart logs ps health test test-frontend lint fmt fmt-eval clean \
        pron-up llm-up llm-check migrate migrate-down migrate-status seed eval eval-local asr-wer \
        tts-latency tts-sample turn-latency turn-latency-noflow pron-golden pron-fetch \
        persona-adherence answer-feedback corpus analyze analyze-dry reparse error-precision rollup \
        rollup-dry rollup-force

help:                              ## This list
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ── First run ───────────────────────────────────────────────────────────────

# Idempotent, so it is also the command to run after a `git pull`. `--wait` waits for
# healthy processes, not for model weights: asr reports healthy while Whisper downloads.
setup:                             ## First run, and after every pull: build, start, migrate, seed
	@test -f .env || { cp .env.example .env && echo "wrote .env from .env.example"; }
	docker compose up -d --build --wait
	docker compose exec api alembic upgrade head
	docker compose exec api python -m scripts.seed
	@echo ""
	@$(MAKE) --no-print-directory llm-check || true
	@echo ""
	@echo "Open http://localhost:3003/register"
	@echo "Use localhost, not a LAN address: browsers only allow the microphone on a secure origin."
	@echo "On a first run asr is still downloading Whisper; \`make health\` shows"
	@echo "\"model_loaded\": true under asr when it is ready."

# Asks the API rather than the host: on Linux the host's Ollama listens on 127.0.0.1, which
# a container cannot reach even when a curl from the host succeeds.
define LLM_CHECK
import json, sys
llm = json.load(sys.stdin)["services"]["llm"]
if llm["status"] == "ok":
    print(f"llm: ok, {llm['reports']['model']} at {llm['url']}")
    sys.exit(0)
print(f"llm: {llm['status']}. {llm.get('detail', '')}")
print("Conversations will not work until this is fixed. Everything else does.")
if llm["status"] == "unreachable":
    print(f"Nothing answered at {llm['url']}, as seen from inside the api container.")
    print("  1. Install Ollama from https://ollama.com/download and start it.")
    print("  2. ollama pull gemma3:4b   (or whatever OLLAMA_MODEL is set to in .env)")
    print("  On Linux, start Ollama with OLLAMA_HOST=0.0.0.0 so containers can reach it.")
print("Then: make llm-check")
sys.exit(1)
endef
export LLM_CHECK

llm-check:                         ## Can the API reach Ollama, with the model pulled?
	@body=$$(curl -sf --max-time 10 http://localhost:8002/health/models) \
		|| { echo "The API is not answering on localhost:8002. Start the stack: make setup"; exit 1; }; \
	echo "$$body" | python3 -c "$$LLM_CHECK"

# ── Everyday ────────────────────────────────────────────────────────────────

up:                                ## Start the default stack (5 services)
	docker compose up -d

# Both profiles, so pron and ollama are removed too; otherwise a stopped pron container
# outlives the network and the next `make pron-up` fails. Naming a profile starts nothing.
down:                              ## Stop everything, pron and ollama included. Volumes survive.
	docker compose --profile pron --profile llm down

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

# `--no-deps`: these tests never call the API, so they do not wait for it.
test-frontend:                     ## Run the frontend suite (Jest + RTL) in a container
	docker compose run --rm --no-deps frontend npm test

# eval/ is mounted read-only inside /app, so it is excluded from the /app pass and checked
# in its own. The two exclusions differ on purpose: ruff's matches a directory name, while
# black's is a regex over the whole path, anchored so it does not also skip
# tests/eval_out.py and tests/test_eval_harness.py.
lint:                              ## ruff + black, check only
	docker compose --profile tools run --rm --entrypoint sh test -c \
		"ruff check --exclude eval /app && black --check --exclude '^/eval/' /app \
		 && ruff check /app/eval && black --check /app/eval"

fmt:                               ## ruff --fix + black, in place
	docker compose --profile tools run --rm --entrypoint sh test -c \
		"ruff check --fix --exclude eval /app && black --exclude '^/eval/' /app"

# Formats eval/ through a separate writable mount, so /app/eval stays read-only for
# everything else, the measurement suites included.
fmt-eval:                          ## ruff --fix + black over eval/, via a writable mount
	docker compose --profile tools run --rm -v "$$PWD/eval:/eval-rw" \
		--entrypoint sh test -c "ruff check --fix /eval-rw && black /eval-rw"

# ── Model services ──────────────────────────────────────────────────────────

pron-up:                           ## Start the pronunciation service (1.78 GB image)
	@echo "Not in the default stack: it is the only image with torch in it. The first"
	@echo "start also downloads 1.2 GB of wav2vec2 weights into the model_cache volume."
	docker compose --profile pron up -d

pron-fetch:                        ## Download the pronunciation probe recording
	@echo "Audio is not stored in git, so the probe recording is downloaded."
	python3 eval/golden/pron/fetch.py

llm-up:                            ## Run Ollama in a container instead of on the host
	@echo "On macOS a container cannot use the GPU, so this runs on the CPU. It is meant"
	@echo "for a Linux host with a GPU, or for CI."
	docker compose --profile llm up -d ollama
	docker compose --profile llm exec ollama ollama pull $${OLLAMA_MODEL:-gemma3:4b}
	@echo ""
	@echo "The API still uses the host's Ollama. To switch, set"
	@echo "  OLLAMA_BASE_URL=http://ollama:11434"
	@echo "in .env, then: make restart && make llm-check"

# ── Data ────────────────────────────────────────────────────────────────────

migrate:                           ## Apply Alembic migrations to the running stack
	docker compose exec api alembic upgrade head

migrate-down:                      ## Roll back one revision. Read the downgrade first.
	docker compose exec api alembic downgrade -1

migrate-status:                    ## Which revision the database is on, and what exists
	@docker compose exec api alembic current
	@docker compose exec api alembic history

seed:                              ## Load the scenarios and passages. Idempotent.
	docker compose exec api python -m scripts.seed

asr-wer:                           ## Measure WER, and mistakes said aloud, against the live asr
	@echo "Needs \`make up\`."
	docker compose --profile tools run --rm \
		-e ASR_URL=http://asr:8101 -e TTS_URL=http://tts:8102 test \
		python -m pytest /app/tests/test_asr_golden.py -v -s

tts-latency:                       ## Measure synthesis latency against the live tts
	@echo "Needs \`make up\`."
	docker compose --profile tools run --rm \
		-e TTS_URL=http://tts:8102 test \
		python -m pytest /app/tests/test_tts_live.py -v -s

tts-sample:                        ## Synthesise a WAV you can listen to
	@mkdir -p spike/tts-sample
	@curl -sf -X POST http://localhost:8102/synthesize \
		-H 'content-type: application/json' \
		-d '{"text":"That sounds like a reasonable plan, though I would want to confirm the delivery date before we commit to anything. Could you check with your supplier and let me know by Friday?"}' \
		-o spike/tts-sample/reply.wav \
		&& echo "wrote spike/tts-sample/reply.wav" \
		|| echo "no answer from http://localhost:8102 — is the stack up?"

turn-latency:                      ## Measure a whole conversational turn, end to end
	@echo "Needs \`make up\` and Ollama on the host. Takes a couple of minutes."
	docker compose --profile tools run --rm \
		-e ASR_URL=http://asr:8101 \
		-e TTS_URL=http://tts:8102 \
		-e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
		test python -m pytest /app/tests/test_conversation_live.py -v -s

turn-latency-noflow:               ## The same, with generation and synthesis in series
	@echo "The control for turn-latency: synthesis starts only after the whole reply."
	docker compose --profile tools run --rm \
		-e ASR_URL=http://asr:8101 \
		-e TTS_URL=http://tts:8102 \
		-e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
		-e LLM_STREAM_TO_TTS=0 \
		test python -m pytest /app/tests/test_conversation_live.py -v -s -k whole_turn

analyze:                           ## Analyse the user turns nothing has analysed yet
	@echo "Needs \`make up\` and Ollama on the host."
	docker compose exec api python -m scripts.analyze_backfill --all

analyze-dry:                       ## List what analysis is outstanding, and stop
	docker compose exec api python -m scripts.analyze_backfill --dry-run

reparse:                           ## Recount forms and relink corrections, no model call
	@echo "After a change to the parser or the form join. Run \`make rollup\` after it."
	docker compose exec api python -m scripts.reparse

error-precision:                   ## Score error detection against the hand-labelled set
	@echo "Needs Ollama on the host. Prints precision and recall; asserts only that the"
	@echo "machinery holds. If the corpus has grown, rebuild the set first:"
	@echo "  docker compose exec api python /app/eval/golden/errors/build.py"
	docker compose --profile tools run --rm \
		-e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
		test python -m pytest /app/tests/test_error_precision.py -v -s

rollup:                            ## Rebuild the progress snapshots every account is owed
	@echo "Ending a session already does this; this catches read-aloud scores and"
	@echo "backfilled turns."
	docker compose exec api python -m scripts.rollup

rollup-dry:                        ## Say which accounts are out of date, and stop
	docker compose exec api python -m scripts.rollup --dry-run

rollup-force:                      ## Recompute every snapshot, not only the stale ones
	@echo "For after a change to the rollup arithmetic. Otherwise use \`make rollup\`."
	docker compose exec api python -m scripts.rollup --force

pron-golden:                       ## Measure GOP against the live pron service
	@echo "Real speech scored against text with planted phone errors; passes at 8 of 10."
	@echo "Needs \`make pron-up\` and \`make pron-fetch\`. About two and a half minutes."
	docker compose --profile tools run --rm \
		-e PRON_URL=http://pron:8103 test \
		python -m pytest /app/tests/test_gop.py -v -s

persona-adherence:                 ## Score persona adherence, and score the judge too
	@echo "Needs Ollama on the host. About three minutes."
	docker compose --profile tools run --rm \
		-e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
		test python -m pytest /app/tests/test_persona_adherence.py -v -s

answer-feedback:                   ## Score how answers are counted, and the model's feedback on them
	@echo "The counting half needs nothing running; the feedback half needs Ollama on the"
	@echo "host. About two minutes."
	docker compose --profile tools run --rm \
		-e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
		test python -m pytest /app/tests/test_answer_measures.py -v -s

corpus:                            ## How much practice the database holds
	docker compose exec api python -m scripts.corpus

eval:                              ## Run every suite that can run, then write docs/evaluation.md
	@echo "A suite whose service is not up is reported as not run, never as passing."
	@echo "For everything to run: \`make up\`, \`make pron-up\` and Ollama on the host."
	python3 eval/run.py

eval-local:                        ## The same harness without Docker, as CI runs it
	@echo "Model-facing suites skip unless their services are up and their URLs exported."
	python3 eval/run.py --local --out /tmp/speaklab-evaluation.md

# ── Destructive ─────────────────────────────────────────────────────────────

clean:                             ## Stop everything and DELETE the database and downloaded models
	docker compose down -v --remove-orphans
