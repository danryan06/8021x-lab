.PHONY: up down logs migrate seed backend-shell frontend-shell ps bootstrap test-peap

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

migrate:
	docker compose exec backend alembic upgrade head

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
