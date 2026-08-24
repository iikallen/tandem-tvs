# Tandem Portal Stage 6 report

Date: 2026-08-24
Scope: Local authentication, sessions and centralized module authorization
Result: **PASS on the local release gate, clean Compose acceptance, security review and external
Cloudflare Access acceptance.** Stage 7 was not started.

## Delivered

- `identity.User` remains the only account model and preserves existing primary keys and all Stage
  1–5 relations. Usernames are required, NFKC-normalized and case-insensitively unique; `portal_id`
  is nullable and immutable after assignment.
- Django local authentication replaces trusted portal-header authentication. Passwords use
  Argon2id, accept 15–128 Unicode characters, and are never stored or logged in plaintext.
- Login has generic failures, per-username and per-client-IP throttling, session/CSRF rotation and
  append-only security events. The trusted client IP header is overwritten by Nginx from
  `CF-Connecting-IP`, with the direct peer address as a fail-closed fallback.
- Production uses `SessionAuthentication`, cached-database sessions, an HttpOnly/Secure/SameSite
  `__Host-tandem_session` cookie, absolute and idle expiry, and server-side invalidation after
  logout, password change/reset or account deactivation.
- Invitation and password-reset capabilities are random, hash-only, expiring and one-use. Unknown
  reset identities return the same response as known identities. Delivery is isolated behind the
  existing development delivery adapter.
- `AccessGrant` is the centralized authorization source for Platform, News and the future Messenger
  entitlement. Editorial, moderation, publishing and discussion endpoints enforce grants on the
  server. Stage 6 exposes only a Messenger access placeholder and does not implement messaging.
- Platform admins can create, search, update, activate/deactivate and recover accounts, and grant or
  revoke allowlisted Platform/News/Messenger roles. Ordinary employees cannot reach these APIs and
  serializers cannot mass-assign credentials, account status or grants.
- Login, activation, reset and platform-management UI are localized, keyboard accessible and
  responsive at 360, 390, 768 and 1440 px. All former portal-projection E2E flows now authenticate
  through the local session boundary.
- Publication recipient snapshots now keep the local user relation as the source of identity, so
  nullable portal IDs cannot break audience history or Stage 5 analytics.

## Automated evidence

- Backend: **131 passed**; **93.28% overall coverage**, **95.81% identity**, **95.74%
  discussions**, **95.54% publications**.
- Ruff format/check, basedpyright (0 errors/warnings/notes), `ty check`, Django check, migration
  drift and production deployment check: PASS.
- Frontend: Prettier, ESLint, TypeScript, **17/17 Vitest tests** and Vite production build: PASS.
- Playwright: **28/28 Chromium E2E tests** passed with one deterministic worker. Eight Stage 6 live
  cases cover login/CSRF, activation, platform administration, grants, deactivation, reset/password
  change session invalidation, responsive layouts and the Messenger entitlement boundary.
- Realtime backend suite: **5/5 passed**; authenticated session tickets, origin checks, one-use,
  scope, expiry and read-only WebSocket behavior remain enforced.
- `npm audit`: 0 vulnerabilities. `pip-audit`: no known vulnerabilities. Bandit medium/high scan:
  no findings. `docker compose config --quiet`: PASS.

## Clean Compose acceptance

Only the project-scoped `tandem-tvs` containers and volumes were removed. Images were rebuilt with
`--no-cache`, then PostgreSQL, Redis, backend, Celery worker, Celery beat and frontend were started
with `--wait`; all six services became healthy.

- Stage 2 verifier: PASS.
- Stage 3 verifier: PASS.
- Stage 4 two-phase verifier after restart: PASS.
- Stage 5 two-phase verifier after restart: PASS; recipients `4`, reach `75.0%`, engagement
  `75.0%`, acknowledgement `50.0%`.
- Stage 6 two-phase verifier after Redis/backend restart: PASS; session persistence, invitation and
  reset one-use/expiry, parallel-session invalidation, inactive-account denial, grants and
  entitlement checks all passed.

Measured clean-run Stage 4 scheduler deviations remained within the required 0–60 second bounds:

```text
publish_delay_seconds: 8.771
unpublish_delay_seconds: 13.771
```

Backend and Redis expose no host ports. The development overlay binds frontend and PostgreSQL only
to `127.0.0.1`; none of backend, PostgreSQL or Redis is directly Internet-accessible.

## Cloudflare evidence

- The existing tunnel `tandem-tvs` was reused; no second tunnel was created. Tunnel ID
  `2c27a4b0-5b7c-4ab8-872e-faece5441ad9` is **Healthy** with one Linux amd64 replica running
  cloudflared `2026.6.1` and four QUIC connections.
- The managed ingress is `tandem-tvs.chatlink.kz` -> `http://frontend:80`. Connector pre-checks for
  DNS, UDP/QUIC, TCP/HTTP2 and Cloudflare API connectivity passed.
- An unauthenticated external HTTPS request was redirected to Cloudflare Access. The configured
  Cloudflare identity provider completed SSO, and the external hostname loaded the real Stage 6
  `Tandem Portal` login page over HTTPS.
- The same Nginx `/ws/` upgrade route remains covered by the 28-test live E2E suite and the five-test
  backend realtime suite; the Stage 5 release had already proven that route through this unchanged
  Cloudflare hostname and Access policy.

## Independent security review

Codex Security diff scan `38d8480e-7ad3-449e-a69b-bee7d72563aa` reviewed all 68 changed source
files with complete coverage. It reported 0 Critical, 0 High and one Medium finding: all clients
behind a shared reverse-proxy IP could consume the global IP login budget. The finding was fixed by
using the Nginx-overwritten Cloudflare client IP header with validated direct-peer fallback, and a
regression test plus live Nginx security-event proof were added. The final tree has **0 unresolved
Critical, High or Major findings**.

## Release boundary

The protected `main` workflow runs the exact `make prod` gate on a clean Ubuntu runner. Stage 6 is
merged only after the required `release-gate` check is green, and `stage-6-complete` is created only
after the exact post-merge run passes. Existing release tags remain unchanged. Stage 7 and Messenger
functionality remain out of scope.
