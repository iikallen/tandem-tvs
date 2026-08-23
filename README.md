# Tandem TVS — Stage 2

Production-shaped Tandem portal module for addressed corporate publications. Stage 2 adds a role-protected editorial workspace, structured rich text, server-side audience authorization, news feed/detail, filters, unread state, unique views, and PostgreSQL full-text search while preserving the Stage 1 portal boundary.

The real portal SSO/API contract is intentionally not invented. Development and tests use a deterministic `MockPortalAdapter`; production will reject that adapter.

## Prerequisites

- Python 3.13
- `uv`
- Node.js 24 LTS and npm
- Docker with Compose (required from the containerization phase)

## Local bootstrap

```sh
cd backend
uv sync --all-groups
uv run python manage.py check

cd ../frontend
npm ci
npm run build
```

The repository-level `Makefile` is the single quality-gate interface:

```sh
make check
make test
make e2e   # requires the local Compose stack on 127.0.0.1:8080
make build
make prod  # runs all of the above plus deploy/config checks
```

## Containers

Local loopback deployment:

```sh
docker compose -f compose.yaml -f compose.local.yaml up -d --build
```

The frontend is then available at `http://127.0.0.1:8080`. PostgreSQL, Redis, and Django are reachable only inside the Compose network. See `docs/cloudflare-deployment.md` for the optional tunnel profile.

## Documentation

- [Stage 1 plan](docs/stage1-plan.md)
- [Architecture](docs/architecture.md)
- [Portal integration questions](docs/portal-integration-questions.md)
- [Portal integration contract](docs/portal-integration-contract.md)
- [Cloudflare deployment](docs/cloudflare-deployment.md)
- [Stage 1 acceptance report](STAGE1_REPORT.md)
- [Stage 2 plan](docs/stage2-plan.md)
- [Stage 2 decisions](docs/stage2-decisions.md)
- [Stage 2 acceptance contract](docs/stage2-acceptance.md)

Source copies and their hashes are recorded in the Stage 1 plan under `references/source/`.
