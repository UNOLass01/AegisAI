.PHONY: up down logs test migrate help

help:
	@echo "Targets: up | down | logs | test | migrate"
	@echo "  (full implementations land in Phase 1)"

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	@echo "Phase 0 placeholder: no tests yet (Phase 1 adds backend tests)."

migrate:
	@echo "Phase 0 placeholder: no migrations yet (Phase 1 adds Alembic)."
