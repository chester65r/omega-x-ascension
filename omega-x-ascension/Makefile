.PHONY: dev test lint up down migrate
dev:
	uvicorn omega.main:app --reload --app-dir src
test:
	pytest -q
lint:
	ruff check . && mypy src
up:
	docker compose up --build -d
down:
	docker compose down
migrate:
	python scripts/migrate.py
