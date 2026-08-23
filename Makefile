UV ?= uv
NPM ?= npm

.PHONY: format check test test-postgres test-stage4 test-realtime e2e build prod

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
	cd backend && POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432 POSTGRES_DB=tandem POSTGRES_USER=tandem POSTGRES_PASSWORD=tandem-development-only $(UV) run pytest
	cd backend && $(UV) run coverage report --include="apps/discussions/*" --fail-under=95
	cd backend && $(UV) run coverage report --include="apps/publications/*" --fail-under=95
	cd frontend && $(NPM) test

test-postgres:
	docker compose exec -T backend uv run --no-sync python manage.py seed_stage2_demo
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage2.py
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage3.py

test-stage4:
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage4.py prepare
	docker compose restart backend celery-worker celery-beat
	docker compose -f compose.yaml -f compose.local.yaml up -d --wait backend celery-worker celery-beat frontend
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage4.py verify

test-realtime:
	cd backend && $(UV) run pytest tests/test_realtime.py --no-cov

e2e:
	docker compose exec -T backend uv run --no-sync python manage.py seed_stage2_demo
	docker compose exec -T backend uv run --no-sync python manage.py seed_stage3_demo
	cd frontend && $(NPM) run test:e2e

build:
	cd frontend && $(NPM) run build

prod: check test test-postgres test-stage4 test-realtime e2e build
	cd backend && $(UV) run python scripts/check_production.py
	docker compose config --quiet
