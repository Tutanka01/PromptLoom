.DEFAULT_GOAL := help

.PHONY: help doctor config start up down status health logs test test-tts

help:
	@echo "PromptLoom"
	@echo "  make doctor    Check Docker and validate the Compose stack (no build)"
	@echo "  make start     Build and start PromptLoom in the background"
	@echo "  make up        Build and run PromptLoom in the foreground"
	@echo "  make status    Show service state"
	@echo "  make health    Query the API health endpoint"
	@echo "  make logs      Follow API and worker logs"
	@echo "  make down      Stop the stack without deleting volumes"
	@echo "  make test      Run video-api tests"
	@echo "  make test-tts  Run the optional TTS server tests"

doctor:
	@command -v docker >/dev/null || { echo "Docker is not installed or not in PATH"; exit 1; }
	@version="$$(docker compose version --short | sed 's/^v//')"; \
	major="$${version%%.*}"; rest="$${version#*.}"; minor="$${rest%%.*}"; \
	if [ "$$major" -lt 2 ] || { [ "$$major" -eq 2 ] && [ "$$minor" -lt 20 ]; }; then \
		echo "Docker Compose >= 2.20 is required (found $$version)"; exit 1; \
	fi; \
	echo "Docker Compose $$version"
	@docker compose config --quiet
	@echo "PromptLoom preflight: OK"

config:
	docker compose config --quiet

start:
	docker compose up --build -d

up:
	docker compose up --build

down:
	docker compose down

status:
	docker compose ps

health:
	@curl -fsS http://localhost:8080/healthz
	@echo

logs:
	docker compose logs -f worker api

test:
	docker compose run --rm test

test-tts:
	docker compose -f apps/tts-server/compose.yaml run --rm test
