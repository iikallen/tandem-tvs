UV ?= uv
NPM ?= npm

.PHONY: format check test test-postgres test-stage4 test-stage5 test-stage6 test-stage7 test-stage8 test-stage9 test-realtime e2e build prod

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
	cd backend && $(UV) run pip-audit
	cd backend && $(UV) run bandit -q -r apps config scripts -x '*/migrations/*' -ll
	cd frontend && $(NPM) run format:check
	cd frontend && $(NPM) run lint
	cd frontend && $(NPM) run typecheck
	cd frontend && $(NPM) audit --audit-level=high

test:
	cd backend && POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432 POSTGRES_DB=tandem POSTGRES_USER=tandem POSTGRES_PASSWORD=tandem-development-only $(UV) run pytest
	cd backend && $(UV) run coverage report --include="apps/identity/*" --fail-under=95
	cd backend && $(UV) run coverage report --include="apps/discussions/*" --fail-under=95
	cd backend && $(UV) run coverage report --include="apps/publications/*" --fail-under=95
	cd backend && $(UV) run coverage report --include="apps/messenger/*" --fail-under=95
	cd backend && $(UV) run coverage report --include="apps/notifications/*" --fail-under=90
	cd backend && $(UV) run coverage report --include="apps/search/*" --fail-under=90
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

test-stage5:
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage5.py prepare
	docker compose restart redis backend celery-worker celery-beat
	docker compose -f compose.yaml -f compose.local.yaml up -d --wait backend celery-worker celery-beat frontend
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage5.py verify

test-stage6:
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage6.py prepare
	docker compose restart redis backend celery-worker celery-beat
	docker compose -f compose.yaml -f compose.local.yaml up -d --wait backend celery-worker celery-beat frontend
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage6.py verify

test-stage7:
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage7.py prepare
	docker compose stop redis
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage7.py outage; stage7_status=$$?; docker compose start redis; exit $$stage7_status
	docker compose restart backend celery-worker celery-beat
	docker compose -f compose.yaml -f compose.local.yaml up -d --wait backend celery-worker celery-beat frontend
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage7.py verify

test-stage8:
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage8.py prepare
	docker compose stop redis
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage8.py outage; stage8_status=$$?; docker compose start redis; exit $$stage8_status
	docker compose restart backend celery-worker celery-beat
	docker compose -f compose.yaml -f compose.local.yaml up -d --wait backend celery-worker celery-beat frontend
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage8.py verify

test-stage9:
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage9.py prepare
	docker compose stop redis
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage9.py outage; stage9_status=$$?; docker compose start redis; exit $$stage9_status
	docker compose restart backend celery-worker
	docker compose -f compose.yaml -f compose.local.yaml up -d --wait backend celery-worker celery-beat frontend
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage9.py verify

test-realtime:
	cd backend && POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432 POSTGRES_DB=tandem POSTGRES_USER=tandem POSTGRES_PASSWORD=tandem-development-only $(UV) run pytest tests/test_realtime.py --no-cov

e2e:
	docker compose exec -T backend uv run --no-sync python manage.py seed_stage2_demo
	docker compose exec -T backend uv run --no-sync python manage.py seed_stage3_demo
	cd frontend && $(NPM) run test:e2e

build:
	cd frontend && $(NPM) run build

prod: check test test-postgres test-stage4 test-stage5 test-stage6 test-stage7 test-stage8 test-stage9 test-realtime e2e build
	cd backend && $(UV) run python scripts/check_production.py
	docker compose config --quiet
