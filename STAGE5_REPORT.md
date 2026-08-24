# Tandem Portal Stage 5 report

Date: 2026-08-24
Scope: Engagement, moderation and analytics
Result: **PASS on the local release gate, clean Compose acceptance and external Cloudflare acceptance.** Stage 6 was not started.

## Delivered

- Two-level discussion threads preserve the exact reply target, expose bounded root/reply cursor
  pages, and load at most two preview replies per root with a windowed database query.
- Comment creation enforces publication visibility, discussion state, active restrictions, edit/delete
  windows, eligible mentions, attachment ownership and category/file limits on the server.
- In-app mention/reply notifications are idempotent. Publication and comment reactions support the
  configured five-type vocabulary while preserving one reaction per user and target.
- Reports, Unicode-normalized stop-word flags, moderation queue, hide/restore/remove tombstones and
  commenter restrictions are available to editor/admin roles. Moderation and restriction actions
  write append-only audit events atomically with their state changes.
- Comment files reuse `MediaAsset`; a user cannot attach another user's asset or reuse media already
  linked to a publication/comment. Hidden/removed comment attachments remain inaccessible to regular
  employees and uploads are scoped to 10 requests/minute.
- Publication policies cover comments, reactions and required acknowledgement. Recipient snapshots
  use the same audience rules as `visible_to`, resolve every supported audience type without per-user
  queries and retain historical acknowledgements.
- Publication/category/department analytics include recipients, unique views, reach, comments,
  reactions, unique engagement and acknowledgement. Global analytics use six bulk queries rather
  than a per-publication query loop. CSV exports protect spreadsheet formula prefixes.
- The employee UI includes threads, reply context, mentions, attachments, moderation placeholders,
  extended reactions, acknowledgement and notifications. Editorial UI includes moderation,
  engagement settings, acknowledgement lists/CSV and analytics/CSV.
- Realtime protocol v2 reconciles REST-backed comments, reactions and moderation events. Nginx now
  resolves the backend through Docker DNS so backend recreation cannot leave a stale upstream IP.

## Automated evidence

- Backend: **115 passed**; **93.14% overall coverage**, **96% discussions**, **95% publications**.
- Stage 5-specific backend suite: **5 passed**, including constant-query recipient/analytics checks,
  all audience types and comment attachment IDOR.
- Ruff format/check, basedpyright, `ty check`, Django check and migration drift: PASS.
- Frontend: Prettier, ESLint, TypeScript, **17 Vitest tests** and Vite production build: PASS.
- Playwright: **20/20 Chromium E2E tests** passed. The live Stage 5 flow covers a targeted
  publication, an excluded outsider, mention/reply notifications, realtime comments/reactions,
  acknowledgement, report, hide/restore, restriction and 360/390/768/1440 px layouts.
- Realtime backend suite: **5 passed**.
- `npm audit`: 0 vulnerabilities. `pip-audit`: no known vulnerabilities. Bandit medium/high scan:
  no findings.
- Production settings check and `docker compose config --quiet`: PASS.

## Clean Compose acceptance

The project-scoped `tandem-tvs` containers and volumes were removed, images were rebuilt with
`--no-cache`, and PostgreSQL, Redis, backend, Celery worker, Celery beat, frontend and `cloudflared`
were started with `--wait`. All services became healthy.

- Stage 2 verifier: PASS.
- Stage 3 verifier: PASS, PostgreSQL source of truth, Redis DB 1, ticket reuse/expiry denied and
  reaction concurrency preserved one row.
- Stage 4 two-phase verifier after backend/worker/beat restart: PASS.
- Stage 5 two-phase verifier after Redis/backend/worker/beat restart: PASS.
- Stage 5 deterministic result: recipients `4`, reach `75.0%`, engagement `75.0%`, acknowledgement
  `50.0%`.

Measured clean-run Stage 4 scheduler deviations remained within the required 0–60 second bounds:

```text
publish_delay_seconds: 9.132
unpublish_delay_seconds: 14.138
```

## Cloudflare evidence

- Tunnel `tandem-tvs` passed DNS, UDP/QUIC, TCP/HTTP2 and Cloudflare API pre-checks and registered
  four QUIC connections. Its ingress is `tandem-tvs.chatlink.kz` → `http://frontend:80`.
- Unauthenticated requests to `/`, both health endpoints and `/api/v1/me` returned HTTP 302 to
  Cloudflare Access.
- An authenticated external browser session loaded the portal over HTTPS as the projected portal
  employee and opened a live publication with `Обновления в реальном времени подключены`; no browser
  console error was recorded. This confirms WSS through Access and the tunnel.
- Backend and Redis have no host ports. The local development overlay binds frontend and PostgreSQL
  only to `127.0.0.1`; none of backend, PostgreSQL or Redis is directly Internet-accessible.

## Review and release boundary

The final security/correctness review specifically checked authorization, cross-publication
threads, mention eligibility, attachment IDOR, moderation privileges, restrictions, stop words,
acknowledgement spoofing/races, audience parity, analytics denominators, CSV injection, query bounds,
realtime payloads and audit immutability. The review found and fixed three Major issues (analytics
N+1, unbounded preview-reply reads and attachment IDOR). The reviewed result has **0 unresolved
Critical and 0 unresolved Major findings**.

The protected `main` release workflow runs the exact `make prod` gate on a clean Ubuntu runner.
`stage-4-complete` remains unchanged. Release tag `stage-5-complete` is created only after the PR,
required `release-gate` and exact post-merge run are green. Stage 6 remains out of scope.
