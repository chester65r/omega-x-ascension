.PHONY: dev test lint typecheck up down migrate
dev:
	uvicorn omega.main:app --reload --app-dir src
test:
	pytest -q
lint:
	ruff check src scripts tests && ruff format --check src scripts tests

typecheck:
	mypy src
up:
	docker compose up --build -d
down:
	docker compose down
migrate:
	python scripts/migrate.py
