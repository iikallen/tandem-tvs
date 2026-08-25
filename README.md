# Tandem TVS Portal

Корпоративная платформа новостей и рабочих коммуникаций ТОО «Тандем ТВС».

Текущий scope включает:

- локальные учётные записи, Argon2, server-side sessions и управляемые `AccessGrant`;
- адресные новости, rich text, media, рубрики, метки и редакционный lifecycle;
- комментарии, реакции, обязательное ознакомление, модерацию и аналитику;
- личные и групповые чаты, каналы, realtime, receipts, поиск и защищённые вложения;
- центр уведомлений, Web Push за feature flag, внутреннюю почтовую доставку и RU/KZ поиск;
- production Compose, one-shot migrations, health/metrics, backup/restore и operational runbooks.

Portal SSO больше не является способом входа: это согласованное изменение Stage 6. `PortalAdapter` может импортировать справочные профиль/оргструктуру, но в production выбран `LOCAL_ONLY`, а `PORTAL_ADAPTER=unavailable`. Публичной регистрации нет.

## Архитектура

```text
Browser
  -> Cloudflare Access / Tunnel (если включены)
  -> Nginx + React SPA
  -> Django ASGI / DRF / Channels
       -> PostgreSQL: business source of truth
       -> protected media volume: binary source of truth
       -> Redis: cache, channel layer, Celery broker
       -> Celery worker / beat
```

Подробности: [`docs/architecture.md`](docs/architecture.md).

## Требования

- Python 3.13 и `uv`;
- Node.js 24 LTS и npm;
- Docker с Compose;
- GNU Make для полного release gate.

## Локальный запуск

```sh
docker compose -f compose.yaml -f compose.local.yaml up -d --build --wait
```

Интерфейс: `http://127.0.0.1:8080`. Development bindings ограничены loopback; PostgreSQL, Redis, backend и workers не публикуются в Internet.

Локальная установка без контейнеров:

```sh
cd backend
uv sync --all-groups
uv run python manage.py check

cd ../frontend
npm ci
npm run build
```

## Quality gate

`Makefile` — единый интерфейс проверок:

```sh
make check
make test
make e2e       # нужен запущенный Compose stack
make build
make prod      # полный Stage 2-10 release gate
```

Полный 300-user и 300-WebSocket profile не запускается на каждом push. CI выполняет короткий smoke; release acceptance запускается отдельно в production-shaped среде и фиксируется только фактическими числами.

## Production deployment

Development `compose.yaml` сам по себе не является production interface. Production всегда использует оба файла и явный env:

```sh
docker compose \
  --env-file /run/secrets/tandem-production.env \
  -f compose.yaml \
  -f compose.prod.yaml \
  config --quiet

docker compose \
  --env-file /run/secrets/tandem-production.env \
  -f compose.yaml \
  -f compose.prod.yaml \
  up -d --build --wait
```

Production Compose требует secrets, hosts/origins, PostgreSQL/Redis/Celery URLs, recovery mode, release metadata и monitoring token; известные development values отклоняются при старте. Миграции выполняет one-shot `migrate`, после которого запускается backend. Images получают immutable tag из полного `APP_GIT_SHA`.

Перед первым deployment прочитайте:

- [`docs/stage10/deployment.md`](docs/stage10/deployment.md);
- [`docs/stage10/rollback.md`](docs/stage10/rollback.md);
- [`docs/stage10/backup-restore.md`](docs/stage10/backup-restore.md);
- [`docs/stage10/monitoring.md`](docs/stage10/monitoring.md);
- [`docs/stage10/incident-response.md`](docs/stage10/incident-response.md).

## Runtime и operations

- public liveness: `GET /api/v1/health/live`;
- public readiness: `GET /api/v1/health/ready`;
- safe release metadata: `GET /api/v1/runtime/meta`;
- token-protected dependency health: `GET /internal/health`;
- token-protected Prometheus exposition: `GET /internal/metrics`;
- media check: `python manage.py verify_media_integrity`;
- backup/isolated restore: `ops/backup/`.

PostgreSQL и media — durable data. Redis допустимо восстановить без восстановления business data; его outage переводит realtime/background delivery в degraded/retry mode, а не делает Redis новой точкой истины.

## Документация и release boundary

- [`docs/stage10/01-tz-traceability.md`](docs/stage10/01-tz-traceability.md) — полная матрица ТЗ и открытые acceptance gates;
- [`docs/stage10/permissions-matrix.md`](docs/stage10/permissions-matrix.md) — endpoint-level access rules;
- [`docs/stage10/capacity-plan.md`](docs/stage10/capacity-plan.md) — connection/storage/load budget;
- [`docs/stage10/data-retention.md`](docs/stage10/data-retention.md) — разрешённая cleanup boundary;
- `STAGE1_REPORT.md` ... `STAGE9_REPORT.md` — неизменяемая историческая evidence.

`stage-10-complete` создаётся только после protected PR, зелёного CI на точном merge SHA и всех фактических Stage 10 acceptance checks. Тег `v1.0.0` не создаётся без формальной приёмки заказчиком; Stage 11 не начинается автоматически.
