UV ?= uv
NPM ?= npm

.PHONY: format check test test-postgres test-realtime e2e build prod

format:
	cd backend && $(UV) run ruff format .
	cd frontend && $(NPM) run format

check:
	cd backend && $(UV) run ruff format --check .
	cd backend && $(UV) run ruff check .
	cd backend && $(UV) run basedpyright
	cd backend && $(UV) run ty check
	cd backend && $(UV) run python manage.py check
	cd backend && $(UV) run python manage.py makemigrations --check --dry-run
	cd frontend && $(NPM) run format:check
	cd frontend && $(NPM) run lint
	cd frontend && $(NPM) run typecheck
	cd frontend && $(NPM) audit --audit-level=high

test:
	cd backend && $(UV) run pytest
	cd backend && $(UV) run coverage report --include="apps/discussions/*" --fail-under=95
	cd frontend && $(NPM) test

test-postgres:
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage2.py
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage3.py

test-realtime:
	cd backend && $(UV) run pytest tests/test_realtime.py

e2e:
	docker compose exec -T backend uv run --no-sync python manage.py seed_stage3_demo
	cd frontend && $(NPM) run test:e2e

build:
	cd frontend && $(NPM) run build

prod: check test test-postgres test-realtime e2e build
	cd backend && $(UV) run python scripts/check_production.py
	docker compose config --quiet
