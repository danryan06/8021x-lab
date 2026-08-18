.PHONY: up down logs migrate seed backend-shell frontend-shell ps bootstrap test-peap lint test

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

migrate:
	docker compose exec backend python -m app.runtime_setup

seed:
	docker compose exec backend python -m app.seed

backend-shell:
	docker compose exec backend /bin/sh

frontend-shell:
	docker compose exec frontend /bin/sh

bootstrap:
	./scripts/bootstrap.sh

test-peap:
	./scripts/test-peap.sh

# Local equivalents of the backend CI job (run from the repo root).
# Uses `python3 -m` so it works whether or not the console scripts are on PATH.
lint:
	python3 -m ruff check backend

test:
	python3 -m pytest backend
