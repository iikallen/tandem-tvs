# Tandem Portal Stage 9 report

Date: 2026-08-25
Scope: Stage 9 notifications and global search, plus Messenger carryovers
Result: **PASS on the local clean-Compose release gate. Stage 10 was not started.**

## Delivered

- Messenger channels distinguish administrators, writers and members. Channel posts, optional
  discussion messages, explicit mentions and rate-limited `@all` are enforced server-side.
  Message search supports text, author, date and attachment filters; exact context routes and
  internal publication previews reauthorize every target.
- The unified PostgreSQL notification domain owns seven event types, durable idempotent fanout,
  unread grouping, global/event/chat preferences, read state, two-device realtime hints and
  external delivery state. Concurrent unread-group creation preserves every occurrence.
- Publication fanout captures the exact publication-time recipient IDs. Push and email workers
  recheck current global, event, membership, mode and mute policy immediately before I/O.
- Web Push uses generic wake-ups only, a browser-vendor host allowlist, standard HTTPS endpoints,
  five subscriptions per user and a 20/hour registration throttle. It remains disabled by default
  pending the customer's external-delivery security decision. Private email contains no message
  body.
- Global PostgreSQL search returns authorized publications, comments, messages, files and
  employees. Russian and Kazakh use separate dictionaries and ranks; GIN and trigram indexes cover
  the searchable fields. Exact destinations independently reauthorize access.
- The frontend provides the global search route, notification bell/center/settings, exact target
  navigation, push opt-in and channel discussion controls using the existing UI and i18n systems.
  Messenger prioritizes the active message-history refresh before the inbox summary so the
  established sub-second realtime gate remains stable.
- Redis failure does not invalidate database sessions or block REST/search. Source rows, fanout,
  notifications and delivery attempts remain durable in PostgreSQL.

## Automated evidence

- The local host does not provide GNU Make, so the `Makefile` target sequence was executed in its
  declared order instead of adding a project dependency. The protected Ubuntu CI runs literal
  `make prod`.
- Backend: **194/194 passed**; **93.49% overall coverage**, **96.00% identity**, **95.14%
  discussions**, **95.60% publications**, **95.03% Messenger**, **93.74% notifications** and
  **94.79% search**.
- Ruff format/check, basedpyright (0 errors), `ty check`, Django checks, migration drift, Bandit and
  the production deployment check: PASS. The schema generator retains its existing non-fatal
  annotation warnings.
- Frontend: Prettier, ESLint including the production-Cyrillic rule, TypeScript, **25/25 Vitest
  tests**, npm audit and the Vite production build (153 modules): PASS.
- Playwright: **38/38 Chromium E2E tests** passed with one deterministic worker. The Stage 7
  sub-second realtime case also passed three consecutive isolated repetitions after the message
  history refresh priority fix.
- `pip-audit`: no known vulnerabilities. `npm audit`: 0 vulnerabilities.
  `docker compose config --quiet`: PASS.

## Compose acceptance

The deployment was rebuilt from clean PostgreSQL/media volumes. All seven Compose services were
healthy, including the isolated Cloudflare tunnel.

- Stage 2 and Stage 3: PASS.
- Stage 4 restart verification: PASS; `publish_delay_seconds=9.410` and
  `unpublish_delay_seconds=14.399`, both inside the required 0–60 second range.
- Stage 5: PASS; recipients `4`, reach `75.0%`, engagement `75.0%`, acknowledgement `50.0%`.
- Stage 6 Redis/backend restart: PASS.
- Stage 7 Redis outage/restart: PASS; the committed message survived and reconnect synchronized.
- Stage 8 Redis outage/restart: PASS; the outbox recovered and authorization boundaries held.
- Stage 9 Redis outage/restart: PASS; source and search stayed available, fanout recovered, and
  injected SMTP/push failures were delivered successfully after recovery.
- Realtime regression subset: **11/11 passed**.

PostgreSQL, Redis and frontend development bindings are limited to `127.0.0.1`. Backend and worker
ports are container-internal. Only frontend joins both the application and tunnel-edge networks;
cloudflared joins only tunnel-edge, and the public route targets `http://frontend:80`.

## Cloudflare evidence

- Named tunnel `tandem-tvs` registered four QUIC connections.
- Anonymous `https://tandem-tvs.chatlink.kz/` access received a Cloudflare Access redirect before
  the origin.
- Through an Access-authorized external browser session, portal login, the five-section global
  search, grouped notification center and Messenger WSS connection all passed without browser
  console errors.

## Independent security review

The Stage 9 diff was reviewed for notification ownership and target reauthorization, search IDOR
and authorization order, membership intervals, deleted/hidden content, Web Push endpoint abuse and
secret leakage, email/private-content leakage, preference and mute races, channel policy and
`@all` bypass, fanout grouping races, publication audience drift, WebSocket spoofing, XSS and CSRF.

Release-significant findings fixed with regression tests include concurrent grouping count loss,
publication-time audience drift, legacy timestamp loss, malformed search cursors, string-form
`@all` throttle bypass, missing channel policy updates, unrestricted/unbounded push subscriptions,
queued-delivery preference bypass and external-only grouping into visible records. **Zero unresolved
Critical, High or Major findings remain.**

## Ponytail ultra audit

The whole repository was audited for over-engineering. Two report-only cleanup candidates remain:
the unused identity delivery protocol/test console implementation and legacy optional frontend
conversation-member fallbacks. Removing both would save approximately 35 lines and no dependency;
neither is release-significant. No required Stage 9 dependency can be replaced by the standard
library or an already-used native facility without removing a requested feature.

## Release boundary

The immutable tags `stage-1-complete` through `stage-8-complete` remain unchanged. Stage 9 is
released from `stage-9-notifications-search` only through protected `main`, after the branch and
exact post-merge `release-gate` runs pass. The annotated `stage-9-complete` tag is created only from
that verified merge commit. Stage 10 remains out of scope.
