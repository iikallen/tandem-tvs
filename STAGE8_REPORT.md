# Tandem Portal Stage 8 report

Date: 2026-08-25
Scope: Stage 7 hardening and Messenger Complete
Result: **PASS on the local clean-Compose and exact `make prod` gates. Stage 9 was not
started.**

## Delivered

- Realtime tickets are bound to one Django session as well as the user security epoch. Normal
  logout closes only that session's sockets; account disable, password reset and sensitive grant
  changes continue to invalidate all sessions and sockets. Session expiry is rechecked by live
  consumers.
- Non-empty recovery email is canonicalized and protected by a case-insensitive partial database
  unique constraint. The migration fails fast on duplicates. Activation and reset capabilities use
  browser-only fragments, are removed from history on mount and receive a `no-referrer` policy.
- Message idempotency uses a canonical payload fingerprint and returns HTTP 422 when a client UUID
  is reused with different content. Realtime changes use a PostgreSQL transactional outbox with
  at-least-once delivery, stable event IDs and frontend event deduplication.
- The inbox uses a stable cursor and bounded summary serializer. Conversation details and paginated
  members are separate. Tests traverse 500 conversations and keep 50 groups with 200 members out
  of the inbox payload.
- Membership history is sequence-aware. History, replies, forwards, search, receipts, pinned
  messages and protected attachments all apply the same join/leave intervals while requiring an
  active current membership.
- Messenger supports replies, privacy-safe forward snapshots, own-message edits and tombstones,
  append-only revisions, aggregate reactions, protected attachments, group administration,
  monotonic delivered/read state, per-user archive/mute/pin/draft state, message pins and GIN-backed
  PostgreSQL full-text search.
- Presence and typing remain ephemeral in Redis. WebSockets enforce one-use tickets, strict input
  schemas, a 512-byte input ceiling, 30 frames/second, five concurrent user sockets, bounded leases
  and session/socket lifetimes. Logs exclude tickets, session keys, passwords and message bodies.
- `/messages` provides desktop inbox/conversation panes and 360/390 px single-pane navigation,
  reply/edit/delete/reaction controls, attachments, member management, presence/typing, delivery
  receipts, search and per-user conversation state using the existing Tandem UI and i18n contracts.

## Automated evidence

- Exact `make prod`: PASS.
- Backend: **174/174 passed**; **93.81% overall coverage**, **95.85% identity**, **95.29%
  discussions**, **95.52% publications** and **96.00% Messenger**.
- Ruff format/check, basedpyright (0 errors), `ty check`, Django checks, migration drift, Bandit and
  the production deployment check: PASS. The production schema generator emits its existing
  non-fatal annotation warnings.
- Frontend: Prettier, ESLint, TypeScript, **22/22 Vitest tests** and Vite production build (151
  modules): PASS.
- Playwright: **36/36 Chromium E2E tests** passed with one deterministic worker, including
  multi-browser Stage 8 message mutation, attachment/group policy, session logout and 360/390 px
  responsive cases.
- `npm audit`: 0 vulnerabilities. `pip-audit`: no known vulnerabilities.
  `docker compose config --quiet`: PASS.

## Compose acceptance

All Stage 2–8 verifiers passed against the rebuilt PostgreSQL, Redis, Django/Channels, Celery and
Nginx services. Every service returned healthy.

- Stage 2: PASS.
- Stage 3: PASS.
- Stage 4 restart verification: PASS; `publish_delay_seconds=8.238` and
  `unpublish_delay_seconds=13.236`, both inside the required 0–60 second range.
- Stage 5: PASS; recipients `11`, reach `27.3%`, engagement `27.3%`, acknowledgement `18.2%`.
- Stage 6 Redis/backend restart: PASS.
- Stage 7 Redis outage/restart: PASS; the PostgreSQL message survived and reconnect synchronized.
- Stage 8 Redis outage/restart: PASS; the durable outbox recovered, attachment IDOR and membership
  boundaries held, and logout remained session-scoped.
- Realtime regression subset: **11/11 passed**.

PostgreSQL, Redis and frontend development bindings are limited to `127.0.0.1`; backend and worker
ports are container-internal. The public tunnel route targets only `http://frontend:80`.

## Cloudflare evidence

- Named tunnel `tandem-tvs` started four QUIC connections. DNS, QUIC, HTTP/2 and Cloudflare API
  connectivity pre-checks passed.
- Managed ingress is `tandem-tvs.chatlink.kz` to `http://frontend:80` with a final 404 fallback.
- Anonymous external access is intercepted by Cloudflare Access before the origin.

## Independent security review

The Stage 8 diff was reviewed for conversation and attachment IDOR, edit/delete ownership,
cross-conversation replies, forward privacy, membership races and stale sockets, join/leave history,
idempotency conflicts, outbox replay/duplication/spoofing, socket exhaustion/flooding, capability URL
leaks, duplicate recovery email, XSS, CSRF and search privacy.

Release-significant findings were fixed with regression tests: unread state after rejoin; hidden
reply and forward references; recovery-email canonicalization on every write path; editorial access
to unattached Messenger uploads; attachment authorization across historical membership intervals;
deleted-message pins; mutable revision records; and unbounded client WebSocket frame rate.
**Zero unresolved Critical, High or Major findings remain.**

## Ponytail ultra audit

The whole repository was audited for over-engineering. No high-return dependency, abstraction or
layer removal was found. Four small cleanup candidates remain deliberately unchanged because this
audit is report-only: one serializer compatibility alias, one unused delivery protocol, one Stage 3
ticket compatibility wrapper used by regression tools, and legacy optional frontend member
fallbacks. None is release-significant.

## Release boundary

The immutable tags `stage-1-complete` through `stage-7-complete` are unchanged. Stage 8 is released
from `stage-8-messenger-complete` only through protected `main`, after the branch and post-merge
`release-gate` runs pass. The new immutable `stage-8-complete` tag is created only after that
post-merge result. Stage 9 remains out of scope.
