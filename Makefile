# SpeakLab — every operation worth having a name.
#
# Three services run by default. The model services are behind profiles because a
# profiled service is excluded from `up` AND from `build`, which is what lets
# docker-compose.yml declare build contexts that m4, m5 and m8 have not created yet.

.PHONY: help up down restart logs ps health test lint fmt clean \
        speech-up pron-up llm-up migrate migrate-down migrate-status seed eval asr-wer

help:                              ## This list
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ── Everyday ────────────────────────────────────────────────────────────────

up:                                ## Start postgres, api and frontend
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

# `--exclude eval` on both, and the reason is structural rather than stylistic. Inside
# the container /app is api/, and eval/ is mounted into it READ-ONLY so that the corpus a
# system is evaluated on cannot be rewritten by the system being evaluated (invariant I7).
# A formatter pointed at /app therefore tries to write to a read-only mount and fails.
# CI lints `api` from the repository root, where eval/ is a sibling and never in scope —
# so this exclusion makes the two agree rather than letting them differ silently.
lint:                              ## ruff + black, check only
	docker compose --profile tools run --rm --entrypoint sh test -c \
		"ruff check --exclude eval /app && black --check --exclude eval /app"

fmt:                               ## ruff --fix + black, in place
	docker compose --profile tools run --rm --entrypoint sh test -c \
		"ruff check --fix --exclude eval /app && black --exclude eval /app"

# ── Model services ──────────────────────────────────────────────────────────

speech-up:                         ## Start asr + tts alongside the default stack (m4, m5)
	docker compose --profile speech up -d

pron-up:                           ## Start the pronunciation service (m8). ~2 GB of torch.
	docker compose --profile pron up -d

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

eval:                              ## Retrieval + scoring evaluation (lands in m11)
	@echo "The evaluation harness is m11. Until it lands this target has nothing to run."
	@echo "The one measurement that exists now is \`make asr-wer\`."
	@exit 1

# ── Destructive ─────────────────────────────────────────────────────────────

clean:                             ## Stop everything and WIPE the database and every
                                   ## downloaded model. Correct after a schema change on
                                   ## an empty project; destructive at any other time.
	docker compose down -v --remove-orphans
