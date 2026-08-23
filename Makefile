UV ?= uv
NPM ?= npm

.PHONY: format check test e2e build prod

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
	cd frontend && $(NPM) test

e2e:
	cd frontend && $(NPM) run test:e2e

build:
	cd frontend && $(NPM) run build

prod: check test e2e build
	cd backend && $(UV) run python scripts/check_production.py
	docker compose config --quiet
