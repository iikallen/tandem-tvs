# Tandem Portal Stage 7 report

Date: 2026-08-24
Scope: Stage 6 security hardening and Messenger Core
Result: **LOCAL AND CLEAN CI RELEASE GATES PASS. External authenticated WSS acceptance and the
protected merge are pending. Stage 8 was not started.**

## Delivered

- Password recovery now has independent normalized-account and trusted-client-IP limits, generic
  responses and asynchronous SMTP delivery through the existing Celery worker. Production SMTP
  recovery requires an HTTPS public base URL, and invitations are restricted to never-activated
  accounts.
- `identity.User.security_epoch` replaces full session-table scans. Sessions checkpoint activity at
  most once per minute and fail closed after a security epoch change. Account deactivation and
  security-sensitive grant changes invalidate existing HTTP and realtime authorization.
- `AccessGrant` has database-enforced module/role combinations. Publication individual audiences
  now use local user IDs; live authorization no longer depends on `PortalAdapter`.
- Realtime ticket, claim, middleware, group and security helpers live in the shared `realtime`
  package. Tickets are one-use, scoped, short-lived and bound to `security_epoch`; open sockets join
  a per-user control group and close immediately on revocation. ORM work uses Channels database
  wrappers so stale connections are recycled after database restarts.
- Nginx accepts `CF-Connecting-IP` only across the dedicated private tunnel network and overwrites
  the application client-IP header. Direct untrusted callers cannot spoof the throttling identity.
- Messenger Core adds UUID direct/group conversations, database-canonical direct pairs,
  memberships, strictly sequenced messages, idempotent client message IDs, sequence pagination,
  server-side unread counts and monotonic read pointers/receipts.
- All Messenger REST operations require an active local Messenger grant and active conversation
  membership. Outsiders and platform admins without membership receive 404 for private resources.
  PostgreSQL commits before Redis notification; a Redis delivery failure cannot roll back a message.
- `/messages` provides inbox, people search, direct/group creation, history, unread/read state,
  optimistic send/retry with the same UUID, one reconnecting socket with bounded exponential
  backoff, and a responsive one-pane mobile layout. The new-conversation dialog traps/restores
  keyboard focus and all user-facing text uses the existing i18n contract.

## Automated evidence

- Backend: **160 passed**; **93.84% overall coverage**, **95.72% identity**, **95.35%
  discussions**, **95.51% publications**, **99.76% Messenger**.
- Ruff format/check, basedpyright (0 errors), `ty check`, Django check, migration drift and the
  production deployment check: PASS. The production schema generator still emits its pre-existing
  non-fatal endpoint annotation warnings.
- Frontend: Prettier, ESLint, TypeScript, **21/21 Vitest tests** and Vite production build (151
  modules): PASS.
- Playwright: **33/33 Chromium E2E tests** passed in 58.2 seconds with one deterministic worker.
  Five Stage 7 cases cover two-browser delivery, persistence, lost-response retry without a
  duplicate, groups/unread/responsive layouts, outsider/admin IDOR and live revocation.
- `npm audit`: 0 vulnerabilities. `pip-audit`: no known vulnerabilities. Bandit medium/high scan:
  no findings. `docker compose config --quiet`: PASS.

## Compose acceptance

All Stage 2–7 verifiers passed against PostgreSQL, Redis, Django/Channels and the running workers.

- Stage 2: PASS.
- Stage 3: PASS.
- Stage 4 two-phase restart: PASS; `publish_delay_seconds=1.779`,
  `unpublish_delay_seconds=6.748` (both inside 0–60 seconds).
- Stage 5 two-phase restart: PASS; recipients `10`, reach `30%`, engagement `30%`,
  acknowledgement `20%`.
- Stage 6 two-phase Redis/backend restart: PASS; the intended session survived, another session was
  invalidated and the disabled account was denied.
- Stage 7 three-phase acceptance: PASS. Direct uniqueness, group membership, ordering,
  idempotency, pagination, read state, privacy, immediate grant/account revocation and actual
  WebSocket delivery passed; measured delivery latency was `0.0265` seconds.
- With Redis stopped, the REST send committed to PostgreSQL. After Redis and backend restart, the
  same message and session remained, the Redis run ID and backend boot time changed, and reconnect
  synchronization found the missed message.

PostgreSQL, Redis and Django have no Internet-facing ports. The local development overlay binds
frontend and PostgreSQL only to `127.0.0.1`; the tunnel route targets only `http://frontend:80`.

## Cloudflare evidence

- The existing named tunnel `tandem-tvs` is healthy and has four QUIC connections. Its managed
  ingress remains `tandem-tvs.chatlink.kz` -> `http://frontend:80`.
- Connector DNS, UDP/QUIC, TCP/HTTP2 and Cloudflare API pre-checks passed.
- Cloudflare Access completed and both external HTTPS health endpoints returned HTTP 200. Ready
  reported database, cache and portal components as healthy.
- Authenticated Tandem login, `/messages` and `wss://` acceptance: **PENDING explicit approval to
  transmit the local demo credential through the external hostname.**

## Independent review

The complete `main...stage-7-messenger-core` diff was reviewed for conversation IDOR, direct-pair
races, group membership and platform-admin bypass, author spoofing, idempotency collisions,
sequence/read-state races, WebSocket ticket and epoch bypass, Redis transaction ordering, XSS,
CSRF, directory exposure, password-reset abuse, trusted-proxy spoofing and invalid grant states.

The review found one release-significant resilience issue: realtime middleware used generic
`sync_to_async` for ORM work and could retain a closed PostgreSQL connection after database
replacement. The middleware now uses `database_sync_to_async`; the following full E2E run passed
33/33, including every realtime scenario. Secret-pattern, unsafe-rendering and diff-integrity scans
were clean. **0 unresolved Critical, High or Major findings remain in the local tree.**

## Release boundary

The branch workflow is named `Stage 7 CI`; its `release-gate` job ran the exact `make prod` command
on clean Ubuntu runners for commit `463add09c48829102645c8846677ef96891f2867`. Both the push and
PR runs passed. The branch will be merged through the protected PR only after external WSS
acceptance, then the exact post-merge commit will be verified before creating `stage-7-complete`.
The immutable `stage-6-complete` and all earlier tags are unchanged. Stage 8 is out of scope.
