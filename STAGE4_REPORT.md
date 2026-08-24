# Tandem Portal Stage 4 hardening report

Date: 2026-08-24
Scope: Stage 4 hardening and UI Kit v2 structural redesign
Result: **PASS on the local release gate and clean Compose acceptance.** Stage 5 was not started.

## Hardening delivered

- Existing `AuditEvent` now records publication, category, tag and media changes with actor,
  timestamp, target identity and complete previous/new JSON states. The migration backfills target
  metadata for existing publication events; the trail remains append-only and has no new API/UI.
- Position groups come exclusively from active portal adapter records. Audience validation rejects
  missing/inactive identifiers and persists the adapter's canonical group name without a local-user
  fallback.
- Publication visibility ignores inactive target units and inactive ancestors during subtree checks.
- Media upload removes a stored file when database persistence fails. Media deletion commits its DB
  row and audit event atomically, then removes the file with `transaction.on_commit()`.
- Rich-text validation enforces `assetImage` → image and `internalVideo` → video while attachments
  retain support for every allowed ready asset.
- Pin create/move uses an inner savepoint and returns a DRF validation response for a concurrently
  occupied slot instead of leaking `IntegrityError` as HTTP 500.
- Scheduled publication reconciliation writes a Redis heartbeat after success. Celery worker health
  uses an address-specific ping; beat health requires a heartbeat newer than 60 seconds after a
  45-second startup grace, matching the 15-second reconciliation period.
- All Stage 4 production UI strings live in the existing i18n catalog. ESLint rejects Cyrillic
  literals in production `.tsx` files outside that catalog while excluding test fixtures.
- Regression coverage includes audit before/after states, position-group fail-closed behavior,
  inactive ancestry, media rollback, media/node compatibility, concurrent pins, scheduler timing and
  Celery heartbeat behavior.

## UI Kit v2 redesign

- The persistent shell now follows the supplied UI Kit's grouped portal/content navigation,
  surface hierarchy, tokenized status treatments and account/footer pattern.
- Home, news and all editorial routes use the same card, page-header, filter and action structure.
- Editorial destinations are directly discoverable in the sidebar; redundant in-page navigation was
  removed.
- The responsive layout was checked at 360, 390, 768 and 1440 px. The five-item mobile navigation
  fits at 360 px without horizontal overflow.
- Visual comparison and QA evidence is stored under `docs/design/`; `design-qa.md` records no open
  P0, P1 or P2 findings.

## Automated evidence

- Backend: **110 passed**; **93.00% overall coverage**, **99% discussions**, **96% publications**.
- Ruff format/check, basedpyright, `ty check`, Django check and migration drift: PASS.
- Frontend: Prettier, ESLint, TypeScript, **15 Vitest tests** and Vite production build: PASS.
- Playwright: **19/19 Chromium E2E tests** passed, including live realtime delivery, editorial
  lifecycle, protected media and responsive overflow checks.
- `npm audit`, `pip-audit` and Bandit: no known dependency vulnerability and no Bandit finding.
- Production settings check and `docker compose config --quiet`: PASS.

## Clean Compose and measured scheduler evidence

A clean `down`, image rebuild and `up --wait` were executed with PostgreSQL, Redis, backend, Celery
worker, Celery beat, frontend and `cloudflared`. Every service became healthy. Stage 2 and Stage 3
verifiers passed. Stage 4 preparation ran before a backend/worker/beat restart; verification after
restart passed with PostgreSQL persistence, Celery Redis DB 2, immutable versions, protected media
authorization and both scheduler bounds intact.

```text
publish_delay_seconds: 11.128
unpublish_delay_seconds: 0.727
accepted range for each actual deviation: 0–60 seconds
```

## Cloudflare evidence

- Tunnel `tandem-tvs` is connected over QUIC and routes `tandem-tvs.chatlink.kz` to
  `http://frontend:80`.
- Unauthenticated external requests to `/`, `/api/v1/health/live` and
  `/api/v1/health/ready` return HTTP 302 to Cloudflare Access.
- Only the frontend and local PostgreSQL development overlay bind to `127.0.0.1`; backend and Redis
  have no host binding. None of backend, PostgreSQL or Redis is directly Internet-accessible.

## Release boundary

The reviewed diff has no unresolved Critical or Major finding. The release workflow runs the exact
`make prod` target on a clean Ubuntu runner before merge. `stage-4-complete` remains unchanged, no
new tag is created, and Stage 5 remains out of scope.
