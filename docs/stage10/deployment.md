# Production deployment runbook

Audience: on-call engineer or DevOps operator with repository, host and Cloudflare access. This procedure targets Linux with Docker Compose. Never use bare `compose.yaml` for production.

## Inputs and change record

Record these before starting:

| Field | Value |
| --- | --- |
| Change/ticket | `PENDING` |
| Release commit (40 hex) | `PENDING` |
| Previous release commit | `PENDING` |
| Operator / UTC start | `PENDING` |
| Production hostname | `PENDING` |
| Backup directory created for this deploy | `PENDING` |
| Schema rollback decision | `PENDING` |

Required access: Git repository, production host, secret store, corporate backup mount, monitoring, Cloudflare tunnel `tandem-tvs` and Access policy. Do not paste secrets into tickets, chat, shell history or logs.

## 1. Prepare exact release

```sh
git fetch --prune --tags origin
git checkout --detach <40-character-release-sha>
git status --short
git rev-parse HEAD
git tag --points-at HEAD
```

`git status --short` must be empty. The SHA must equal the approved protected-main commit. Do not deploy a branch tip, dirty tree or mutable `latest` image.

Create an operator-owned, POSIX-shell-compatible `KEY=value` env file outside the repository,
mode `0600`. Quote values that contain shell metacharacters. It must define at least:

- `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`;
- `DATABASE_URL`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`;
- separate `REDIS_URL`, `REALTIME_REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` databases;
- `REALTIME_ALLOWED_ORIGINS`, `AUTH_RECOVERY_MODE`, `AUTH_PUBLIC_BASE_URL`;
- `APP_VERSION=1.0.0` and `APP_GIT_SHA=<exact release SHA>`;
- `OPS_MONITORING_TOKEN` of at least 32 characters;
- `WEB_PUSH_ENABLED` and `NOTIFICATION_EMAIL_ENABLED` explicitly `true` or `false`;
- `CLOUDFLARE_TUNNEL_TOKEN` for the named tunnel.

If `AUTH_RECOVERY_MODE=SMTP` or `NOTIFICATION_EMAIL_ENABLED=true`, also set a real
`DEFAULT_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS=true|false` and either both or
neither of `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`. Placeholder, development and weak secret values
are rejected before Compose starts.

Production Compose fixes `AUTH_MODE=LOCAL_ONLY`, `PORTAL_ADAPTER=unavailable`, `ALLOW_BOOTSTRAP_LOCAL_ADMIN=false` and an empty demo password. Do not override those values.

## 2. Preflight without disclosing configuration

```sh
prod_env=/run/secrets/tandem-production.env
set -a
. "$prod_env"
set +a
test "$(git rev-parse HEAD)" = "$APP_GIT_SHA"

docker compose \
  --env-file "$prod_env" \
  -f compose.yaml \
  -f compose.prod.yaml \
  config --quiet

make prod
```

The exported operator values are intentional: `backend/scripts/check_production.py` validates the
current deployment environment and does not substitute check-only secrets. Do not run
`docker compose config` without `--quiet` in a shared log because rendered environment may contain
secrets. `make prod` must be green on the exact release candidate before deployment; the protected
CI run remains the authoritative shared evidence.

Confirm free capacity before changing the service:

```sh
df -h
docker system df
```

Do not prune automatically during a deployment. If capacity is insufficient, stop and follow the incident/change process.

## 3. Backup before change

Follow [`backup-restore.md`](backup-restore.md). The backup must include PostgreSQL and protected media, live on a separate corporate mount, pass SHA-256 verification and have its directory recorded above. A failed or unverified backup stops deployment.

## 4. Build immutable images

```sh
docker compose \
  --env-file "$prod_env" \
  -f compose.yaml \
  -f compose.prod.yaml \
  build --pull

docker image inspect "tandem-tvs-backend:$(git rev-parse HEAD)" \
  --format '{{json .Config.Labels}}'
docker image inspect "tandem-tvs-frontend:$(git rev-parse HEAD)" \
  --format '{{json .Config.Labels}}'
docker image inspect "tandem-tvs-postgres:$(git rev-parse HEAD)" \
  --format '{{json .RepoTags}}'
```

Verify backend/frontend OCI version/revision labels and the exact PostgreSQL SHA tag. Preserve all
three current and previous SHA-tagged images until the observation window ends.

## 5. Start and migrate once

```sh
docker compose \
  --env-file "$prod_env" \
  -f compose.yaml \
  -f compose.prod.yaml \
  up -d --wait
```

Expected order: PostgreSQL healthy -> one-shot `migrate` completes -> backend healthy -> worker/beat/frontend/tunnel start. The backend entrypoint never migrates. Verify the migration job succeeded exactly once:

```sh
docker compose \
  --env-file "$prod_env" \
  -f compose.yaml \
  -f compose.prod.yaml \
  ps -a

docker compose \
  --env-file "$prod_env" \
  -f compose.yaml \
  -f compose.prod.yaml \
  logs --no-log-prefix migrate
```

If migration fails, do not repeatedly restart it. Preserve logs, stop the rollout and use the schema decision tree in [`rollback.md`](rollback.md).

## 6. Technical smoke

From the production hostname, through Cloudflare Access:

```sh
curl -fsS https://<hostname>/api/v1/health/live
curl -fsS https://<hostname>/api/v1/health/ready
curl -fsS https://<hostname>/api/v1/runtime/meta
```

Expected: live 200; ready 200 with PostgreSQL/media usable; runtime version `1.0.0` and the exact deployed SHA. Inspect response headers for valid HTTPS, HSTS, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Permissions-Policy` and enforced CSP.

Use the monitoring token only from the monitoring/admin network:

```sh
curl -fsS -H "Authorization: Bearer <ops-token>" \
  https://<hostname>/internal/health
curl -fsS -H "Authorization: Bearer <ops-token>" \
  https://<hostname>/internal/metrics
```

The unauthenticated versions must be denied. Detailed health must not reveal URLs, credentials, message bodies or queue payloads.

## 7. Product smoke

Use a non-admin employee plus least-privilege editorial and Messenger accounts:

1. Login and logout; verify the browser stores no bearer credential.
2. Open addressed feed and a publication; verify a non-recipient direct URL is denied.
3. Create/read a comment and reaction; observe another session refresh without reload.
4. Send a direct message and file; verify delivery/read state and foreign-user file denial.
5. Open notifications and mark one read on a second device.
6. Search RU and KZ terms across authorized sections; verify a private target is absent.
7. Establish Messenger and notification WebSockets and reconnect once.
8. Run the production verifier inside the deployed backend container:

   ```sh
   docker compose --env-file "$prod_env" -f compose.yaml -f compose.prod.yaml \
     exec -T backend uv run --no-sync python scripts/verify_stage10.py
   ```

Record actual IDs only in the private change record; do not put message bodies or tokens in shared evidence.

## 8. Cloudflare and origin checks

- Tunnel name is exactly `tandem-tvs` and has healthy connector connections.
- Anonymous request is intercepted by Cloudflare Access before origin content.
- Authorized browser reaches the exact release metadata and WSS.
- PostgreSQL, Redis and backend have no public ports; only Nginx is reachable through the tunnel network.
- A direct-origin attempt cannot bypass Access.

Additional connectors on this same host do not prove host-level HA.

The production overlay bounds PostgreSQL connection and statement waits, rotates every service's
Docker JSON logs, and gives the backend container health probe a five-second timeout. The media
writability check uses filesystem syscalls that Python cannot safely interrupt; Docker's external
health timeout is the hard bound. Treat an unhealthy backend as a storage incident rather than
waiting indefinitely on an in-process probe.

## 9. Accept or rollback

Accept only when health, product smoke, backlogs, media check, security headers and external tunnel checks pass. Watch the release for at least the change-window duration and compare 5xx, p95 latency, outbox/fanout age, heartbeat and media gauges with baseline.

If any gate fails, follow [`rollback.md`](rollback.md). Do not improvise a database downgrade. Complete the change record with UTC end, exact SHA, backup, observed metrics and decision.
