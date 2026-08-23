# Stage 3 acceptance

The release gate is successful only when every applicable item is evidenced:

- The branch is `stage-3-discussions-reactions`; `stage-2-complete` is unchanged.
- Stage 2 hardening is complete and its PostgreSQL/live-browser acceptance runs in CI.
- Comments satisfy visibility, ownership, normalization, stable pagination and soft deletion.
- Reactions allow only `LIKE`, are idempotent and concurrency-safe, with real aggregate counters.
- Invisible, draft, unknown and blocked access is denied server-side without existence leaks.
- Tickets are random, hashed, scoped, one-time and short-lived; Origin is validated.
- WebSocket events are versioned, read-only, commit-only hints; rollback emits nothing.
- React reconciles REST caches on events and after reconnect, with bounded backoff and terminal
  handling for authorization/not-found failures.
- PostgreSQL/Redis acceptance and live Playwright demonstrate two-user realtime and persistence.
- Layouts 360/390/768/1440 and accessibility checks pass.
- `make prod`, production checks, migration drift, audit, Compose config and build pass cleanly.
- Cloudflare Access proves HTTP and WSS externally while backend, PostgreSQL and Redis remain
  unavailable directly from the Internet.
- Independent security review has no unresolved Critical or Major finding.
- `STAGE3_REPORT.md` contains only executed commands and factual PASS/FAIL evidence.
