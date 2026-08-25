UV ?= uv
NPM ?= npm
K6_IMAGE ?= grafana/k6:1.2.3
LOAD_BASE_URL ?= http://127.0.0.1:8080
LOAD_WS_BASE_URL ?= ws://127.0.0.1:8080
FAULT_PROJECT_NAME ?= stage10-fault-local

.PHONY: format check test test-postgres test-stage4 test-stage5 test-stage6 test-stage7 test-stage8 test-stage9 test-stage10 test-realtime backup-drill load-smoke load-full load-websocket profile-db fault-matrix e2e build prod

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
	cd backend && DATABASE_URL= POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=$${POSTGRES_PORT:-5432} POSTGRES_DB=$${POSTGRES_DB:-tandem} POSTGRES_USER=$${POSTGRES_USER:-tandem} POSTGRES_PASSWORD=$${POSTGRES_PASSWORD:-tandem-development-only} REDIS_URL=redis://127.0.0.1:6379/0 REALTIME_REDIS_URL=redis://127.0.0.1:6379/1 CELERY_BROKER_URL=redis://127.0.0.1:6379/2 CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2 $(UV) run pytest
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

test-stage10:
	docker compose exec -T backend uv run --no-sync python scripts/verify_stage10.py

backup-drill:
	sh ops/backup/test-backup-restore.sh

load-smoke:
	load_password=$$(cd backend && $(UV) run python -c 'import secrets; print(secrets.token_urlsafe(24))') && \
	docker compose exec -T -e TANDEM_LOAD_PASSWORD=$$load_password backend uv run --no-sync python manage.py seed_load_profile --users 10 --publications 10 --messages 100 --notifications 100 --confirm-load-environment && \
	docker run --rm --network host -e PROFILE=smoke -e BASE_URL=$(LOAD_BASE_URL) -e WS_BASE_URL=$(LOAD_WS_BASE_URL) -e LOAD_USER_COUNT=10 -e TANDEM_LOAD_PASSWORD=$$load_password -v "$(CURDIR)/load/k6:/scripts:ro" $(K6_IMAGE) run /scripts/stage10.js && \
	docker compose exec -T backend uv run --no-sync python manage.py verify_load_state --minimum-load-users 10 --minimum-messages 100 --require-k6-writes

load-full:
	load_password=$$(cd backend && $(UV) run python -c 'import secrets; print(secrets.token_urlsafe(24))') && \
	docker compose exec -T -e TANDEM_LOAD_PASSWORD=$$load_password backend uv run --no-sync python manage.py seed_load_profile --confirm-load-environment && \
	docker run --rm --network host -e BASE_URL=$(LOAD_BASE_URL) -e WS_BASE_URL=$(LOAD_WS_BASE_URL) -e TANDEM_LOAD_PASSWORD=$$load_password -v "$(CURDIR)/load/k6:/scripts:ro" $(K6_IMAGE) run /scripts/stage10.js && \
	docker compose exec -T backend uv run --no-sync python manage.py verify_load_state --require-k6-writes

load-websocket:
	: "$${OPS_MONITORING_TOKEN:?OPS_MONITORING_TOKEN is required}"
	load_password=$$(cd backend && $(UV) run python -c 'import secrets; print(secrets.token_urlsafe(24))') && \
	docker compose exec -T -e TANDEM_LOAD_PASSWORD=$$load_password backend uv run --no-sync python manage.py seed_load_profile --confirm-load-environment && \
	docker run --rm --network host -e BASE_URL=$(LOAD_BASE_URL) -e WS_BASE_URL=$(LOAD_WS_BASE_URL) -e TANDEM_LOAD_PASSWORD=$$load_password -e OPS_MONITORING_TOKEN="$${OPS_MONITORING_TOKEN}" -v "$(CURDIR)/load/k6:/scripts:ro" $(K6_IMAGE) run /scripts/websocket-capacity.js && \
	docker compose exec -T backend uv run --no-sync python manage.py verify_load_state

profile-db:
	docker compose exec -T backend uv run --no-sync python manage.py profile_database

fault-matrix:
	FAULT_TEST_CONFIRMATION=isolated-environment TANDEM_ENVIRONMENT_PURPOSE=stage10-load python3 ops/fault/run-matrix.py --project-name $(FAULT_PROJECT_NAME) --compose-file compose.yaml --compose-file compose.prod.yaml --compose-file compose.local.yaml

test-realtime:
	cd backend && DATABASE_URL= POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=$${POSTGRES_PORT:-5432} POSTGRES_DB=$${POSTGRES_DB:-tandem} POSTGRES_USER=$${POSTGRES_USER:-tandem} POSTGRES_PASSWORD=$${POSTGRES_PASSWORD:-tandem-development-only} REDIS_URL=redis://127.0.0.1:6379/0 REALTIME_REDIS_URL=redis://127.0.0.1:6379/1 CELERY_BROKER_URL=redis://127.0.0.1:6379/2 CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2 $(UV) run pytest tests/test_realtime.py --no-cov

e2e:
	docker compose exec -T backend uv run --no-sync python manage.py seed_stage2_demo
	docker compose exec -T backend uv run --no-sync python manage.py seed_stage3_demo
	cd frontend && $(NPM) run test:e2e

build:
	cd frontend && $(NPM) run build

prod: check test test-postgres test-stage4 test-stage5 test-stage6 test-stage7 test-stage8 test-stage9 test-stage10 test-realtime e2e build
	cd backend && $(UV) run python scripts/check_production.py
	docker compose -f compose.yaml -f compose.prod.yaml config --quiet
