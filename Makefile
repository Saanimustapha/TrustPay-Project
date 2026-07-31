.PHONY: install dev up down migrate revision upgrade test lint

install:
	python -m venv .venv
	. .venv/bin/activate && pip install -e ".[dev]"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

up:
	docker compose up -d db redis

down:
	docker compose down

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(m)"

upgrade:
	alembic upgrade head

test:
	pytest -v --asyncio-mode=auto

lint:
	ruff check . && ruff format .