# Tandem Portal Stage 3 acceptance report

Date: 2026-08-23  
Scope: Stage 3 — «Обсуждения, реакции и realtime»  
Release candidate: `e825bfbc3bd482957f3c43b4d706a9a94c56f458`  
Result: **PASS.** The Stage 3 implementation, clean CI deployment, PostgreSQL/Redis
acceptance, live two-user browser flow, external Cloudflare HTTP/WSS checks, and independent
security review passed. Stage 4 was not started.

## Delivered vertical slice

- A separate `discussions` domain owns UUID comments and reactions. Comments support create,
  cursor-list, author-only edit, idempotent soft delete, control-character normalization,
  5,000-character validation, and newest-first live pagination.
- The only enabled reaction is `LIKE`, matching the mandatory Stage 3 action in the source
  specification. PUT/DELETE are idempotent and a database uniqueness constraint prevents
  duplicates under concurrent PostgreSQL requests.
- Feed and detail counters are real database aggregates. Independent correlated subqueries
  avoid a `views × comments × reactions` join explosion and preserve constant query shape.
- All discussion, reaction, ticket, and WebSocket paths reuse the canonical
  `Publication.objects.visible_to(user)` authorization boundary. An outside employee receives
  `404`; a blocked employee is denied server-side.
- REST remains the mutation and source-of-truth path. Versioned WebSocket events are read-only
  reconciliation hints emitted only after a successful SQL commit.

## Realtime and ticket security

- Django Channels 4.3.2 and `channels-redis` 4.3.0 use the stable `RedisChannelLayer` on logical
  Redis DB 1; application cache remains on DB 0. Production settings reject any other DB
  assignment or malformed Redis URL.
- A ticket contains at least 256 bits of randomness. Redis stores only its SHA-256 key, applies
  a 30-second TTL, and consumes it atomically with `GETDEL`.
- Ticket claims are derived server-side, bound to one user and publication, and strictly
  validated. Tests cover replay, expiry, wrong-publication scope, malformed input, invisible
  publications, blocked users, and group cleanup.
- WebSocket Origin is validated against an exact allowlist. The socket accepts only `ping`, has
  a 15-minute lifetime, returns controlled close codes, and rejects malformed JSON and binary
  messages. Uvicorn limits frames to 512 bytes before application buffering.
- `/ws/` is proxied with Nginx upgrade headers. Uvicorn and the Nginx WebSocket location disable
  access logging so query-string tickets are not written to access logs.
- A channel-layer outage after commit is handled by a robust `transaction.on_commit` callback:
  the durable REST mutation does not become a false `500`, and PostgreSQL remains authoritative.

## Employee UI

- Publication detail includes an accessible `aria-pressed` like control, comment composer,
  length counter, empty/loading/error states, author/title/time metadata, edited state,
  deleted placeholder, and author-only edit/delete actions.
- TanStack Query performs optimistic reaction updates with rollback and reconciles publication,
  comments, reactions, and feed caches after every local mutation and WebSocket hint.
- Reconnection uses bounded 1/2/5/10/30-second backoff with jitter and stops for terminal
  authentication, authorization, and not-found responses.
- The editor no longer defaults to `ALL`; it supports multiple organization, employee, and
  module-role targets while making the broad audience choice explicit.
- User-facing Stage 2/3 strings are routed through i18n. Responsive checks pass at 360, 390,
  768, and 1,440 px without horizontal overflow.

## Automated release gate

GitHub Actions run `32642016714` completed successfully for the release candidate on a clean
Ubuntu runner. The workflow installed locked Python/Node dependencies, built and started a new
Compose deployment, and executed the repository target literally:

```text
make prod
```

Observed results:

- Ruff format/check: 88 backend files passed.
- basedpyright: 0 errors, 0 warnings, 0 notes; `ty check` passed.
- Django system and deploy checks: no issues; migration drift: no changes.
- Backend: 69 tests passed; total coverage 90.81% with an 88% gate.
- Stage 3 discussions domain coverage: 99% with a 95% gate.
- Focused realtime suite: 5 tests passed.
- PostgreSQL Stage 2 acceptance: `PASS`.
- PostgreSQL/Redis Stage 3 acceptance: `PASS`, including ticket expiry/replay denial,
  concurrent one-row reaction creation, real counters, persistence, and outside-user `404`.
- Prettier, ESLint, TypeScript, and `npm audit --audit-level=high`: passed; 0 vulnerabilities.
- Frontend: 15 Vitest tests passed.
- Playwright: 17 live Chromium E2E tests passed, including the two-addressed-user realtime flow
  and all four responsive viewports. Stage 3 E2E uses the running backend and no route mocks.
- Vite production build and `docker compose config --quiet`: passed.

Two preceding CI attempts correctly failed the release gate and were not accepted: the first
exposed a missing deterministic Stage 2 seed on an empty database; the second exposed an
incorrect global coverage requirement on the repeated five-test realtime subset. Both gate
definitions were corrected without weakening the full-suite or Stage 3 coverage thresholds.

## Local PostgreSQL, Redis, and persistence evidence

After review remediation, the local deployment was rebuilt without Docker cache and brought to
healthy state. The final executable acceptance sequence was:

```text
docker compose -f compose.yaml -f compose.local.yaml build --no-cache
docker compose -f compose.yaml -f compose.local.yaml up -d --wait --wait-timeout 180
docker compose exec -T backend uv run --no-sync python manage.py seed_stage2_demo
docker compose exec -T backend uv run --no-sync python scripts/verify_stage2.py
docker compose exec -T backend uv run --no-sync python scripts/verify_stage3.py
docker compose exec -T backend uv run --no-sync python manage.py seed_stage3_demo
npm run test:e2e
```

PostgreSQL and Redis DB 1 were used by the Stage 3 verifier. It returned `PASS` for normalized
comment persistence, A/B visibility, outside-user `404`, idempotent and concurrent reactions,
real counters, single-use and expired tickets, and a fresh database connection. A separate
backend restart preserved the previously created comment. The final Playwright run reported
17/17 passed.

## Cloudflare and network isolation evidence

- Named tunnel: `tandem-tvs`; tunnel ID
  `2c27a4b0-5b7c-4ab8-872e-faece5441ad9`.
- Public hostname: `https://tandem-tvs.chatlink.kz`; ingress target: `http://frontend:80`.
- `cloudflared` is running with four QUIC connections. The token is supplied only through the
  process environment and is not printed, committed, or written to a project file.
- An unauthenticated client received a Cloudflare Access `302`, while the authenticated browser
  received `200` from live/readiness endpoints. Readiness reported database, cache, and portal
  components `ok`.
- Through the external hostname, the Stage 3 publication rendered its persisted comment and
  reaction, and the page reported `Обновления в реальном времени подключены`, proving the WSS
  upgrade through Cloudflare and Nginx.
- Compose publishes only Nginx on `127.0.0.1:8080`. Connection probes to host ports 8000, 5432,
  and 6379 failed; backend, PostgreSQL, and Redis have no host bindings.

The external proof uses the deterministic development portal projection. Production settings
continue to reject `MockPortalAdapter` and fail closed until the authoritative portal adapter is
configured.

## Independent security review

The independent Stage 3 review found three Major issues during implementation:

1. a Redis failure in an ordinary post-commit callback could turn an already durable mutation
   into a false REST `500`;
2. the ASGI server accepted a much larger WebSocket frame before the 512-byte application check;
3. three aggregate joins caused multiplicative database work as views, comments, and reactions
   accumulated.

All three were fixed with regression coverage: robust commit callbacks, protocol-level frame
limits, and independent correlated count subqueries. The review also drove strict ticket body
validation, complete REST cache reconciliation, newest-first live pagination, controlled
malformed-JSON handling, DB 0/DB 1 enforcement, and fresh edit-state initialization. Its final
security/correctness verdict was **GO with 0 unresolved Critical and 0 unresolved Major**. The
two remaining evidence requests were then implemented and passed in CI: exhaustive ticket/socket
cases and concurrent PostgreSQL reaction uniqueness.

## Release boundary

Stage 3 ends at discussions, the mandatory `LIKE` reaction, and read-only realtime hints.
Messenger delivery, private/group chats, moderation workflows, notification delivery,
analytics, and all other Stage 4 work are intentionally absent. This history is merged to
`main` and tagged `stage-3-complete` only after the report commit itself receives green CI.
