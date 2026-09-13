.PHONY: up down logs test migrate help

help:
	@echo "Targets: up | down | logs | test | migrate"

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd backend && python -m pytest -q

migrate:
	cd backend && alembic upgrade head
