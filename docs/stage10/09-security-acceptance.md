# Stage 10 security acceptance

Historical Stage 9 review reported zero unresolved Critical/High/Major findings for the Stage 9 scope. Stage 10 diff scan `13c6a35e-3325-4a62-93d2-1f14ce11caee` reviewed 134/134 change receipts across eight security surfaces and reported zero findings. Independent reviewer and live operational sign-off remain `PENDING`; see [`../../STAGE10_REPORT.md`](../../STAGE10_REPORT.md).

## Review matrix

| Area                        | Required control/evidence                                                                                         | Result                                                                                                                     |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Production settings bypass  | `config.settings.production`; missing/unsafe values stop startup; `check --deploy`                                | `PASS` — production preflight and release gate                                                                             |
| Development defaults        | No development secret/password, demo admin/password, mock adapter, localhost/wildcard production origin           | `PASS` — fail-fast configuration tests and rendered Compose                                                                |
| Release identity            | Semantic `APP_VERSION`, exact 40-hex SHA, immutable image labels/tags                                             | `PASS` — runtime and image metadata verified                                                                               |
| Host/proxy/origin           | Allowed hosts/origins exact; trusted Cloudflare client IP only from tunnel subnet; direct origin blocked          | `PARTIAL` — configuration/local isolation PASS; external bypass pending                                                    |
| HTTPS/headers               | Valid TLS, HSTS, nosniff, DENY frame, Permissions-Policy; CSP enforced after clean browser audit                  | `PARTIAL` — config and TLS PASS; authorized browser header sweep pending                                                   |
| XSS/rich text               | Structured allowlist, safe links/media node kinds, no `unsafe-eval`; no unexplained CSP violations                | `PARTIAL` — automated policy PASS; authorized CSP browser sweep pending                                                    |
| CSRF/session                | HttpOnly/Secure/SameSite session, CSRF on mutations, rotation, idle/absolute expiry, security-epoch invalidation  | `PASS` — regression and production smoke                                                                                   |
| Password/recovery           | Argon2, generic denial, throttles, hash-only expiring one-use capabilities, no secret logs/URL query token        | `PASS` — regression suite                                                                                                  |
| WebSocket auth              | Exact origin, one-use session-bound scoped ticket, epoch/expiry/socket limit, no private payload in Redis         | `PASS` — regression, mixed load and 300-WSS                                                                                |
| News/comment IDOR           | Addressed queryset before detail/comment/reaction/ack/search/media                                                | `PASS` — cross-module permission suite                                                                                     |
| Private-message IDOR        | Membership intervals for inbox/history/context/search/reply/forward/file; Platform Admin has no bypass            | `PASS` — cross-module permission suite                                                                                     |
| Channel permissions         | Admin/writer/member mutation policy, bounded `@all`, membership changes audited                                   | `PASS` — permission and audit suites                                                                                       |
| Notification/search IDOR    | Recipient-only notifications; every search section and destination independently reauthorize                      | `PASS` — permission and search suites                                                                                      |
| Media                       | Signature/type/size checks, non-executable/private response, safe storage path, rollback-safe file lifecycle      | `PASS` — media validation/IDOR/rollback suites                                                                             |
| Audit                       | Security/business/application logs separated; business/security audit append-only and previous/new state complete | `PASS` — append-only audit suites                                                                                          |
| Backup permissions/secrets  | `0700`/`umask 077`, separate mount, no URL output, safe manifest/tar, production restore refusal                  | `PASS` — script tests and isolated restore drill                                                                           |
| Metrics/log privacy         | Monitoring bearer token; stable low-cardinality labels; no IDs, credentials, cookies, endpoints or bodies         | `PASS` — monitoring tests and sanitized evidence scan                                                                      |
| Outbox/retry exhaustion     | Pending work never deleted by cleanup; bounded retry/alerts; duplicates blocked transactionally                   | `PASS` — cleanup, retry and fault recovery suites                                                                          |
| Disk full/read-only media   | Ready fails; upload rollback preserves DB/file consistency; recovery and verifier documented                      | `PASS` — automated rollback/full-disk coverage plus live read-only readiness 503 and verified recovery                     |
| DB pool exhaustion          | Measured connection budget/headroom under 300-user and WSS profiles                                               | `PASS` — peak 23/400 mixed and 6/400 WSS; rollback/deadlock 0                                                              |
| Load-test authorization     | Seed/users/secrets isolated; load endpoints are normal authorized APIs; no production private-content capture     | `PASS` — isolated `stage10_load_*` database and normal session/ticket APIs                                                 |
| Optional delivery           | Internal SMTP; Web Push disabled without customer approval, generic payload and vendor allowlist                  | `OPS_DEPENDENT` — customer infrastructure/approval                                                                         |
| Cloudflare bypass/HA claims | Access before origin; only Nginx on tunnel network; same-host connectors not described as host HA                 | `PARTIAL` — Access/DNS/TLS and local no-published-port checks passed; authorized tunnel and external bypass checks pending |

## Required automated regression

- production configuration/Compose and API-doc default tests;
- all-role parametrized permissions and direct-object IDOR cases;
- Platform Admin denial for private conversation, message, attachment and search;
- WebSocket ticket/origin/session invalidation;
- media upload/delete transaction rollback and unsafe file/rich-text nodes;
- append-only audit previous/new state;
- monitoring-token, safe health, metrics label/payload and alert-rule checks;
- backup manifest/archive/traversal/production-target refusal;
- cleanup selection boundaries and pending-row preservation;
- connection/load/fault acceptance without lost or duplicate durable mutations.

Actual test counts and commands belong in `STAGE10_REPORT.md`, not in this plan.

## Manual acceptance

1. Review the entire Stage 10 diff independently from the implementer.
2. Exercise external Cloudflare Access, origin isolation, TLS/headers and WSS.
3. Run browser flows at 360/390/768/1440, keyboard-only, screen-reader labels, reduced motion and loading/empty/403/404/500/degraded states.
4. Inspect sanitized logs/metrics/backups for secrets and private content.
5. Run production-shaped load, fault matrix and isolated restore.
6. Re-run exact `make prod` after fixes.

Item 3 is locally complete: 84/84 role-correct main product surface/viewport cells had no
horizontal overflow; keyboard focus, accessible names, reduced motion and every listed state were
exercised. The authorized external CSP/header sweep remains item 2, not part of this local PASS.

## Sign-off

| Field               | Value                                                                                               |
| ------------------- | --------------------------------------------------------------------------------------------------- |
| Reviewer            | Codex Security diff scan; independent human reviewer `PENDING`                                      |
| Reviewed commit     | `bf668a5a611de60cd30e788062f7ba67cf3842e8`; follow-up operational/browser fixes reviewed separately |
| Critical unresolved | `0`                                                                                                 |
| High unresolved     | `0`                                                                                                 |
| Major unresolved    | `0`                                                                                                 |
| Full gate rerun     | `PASS` — CI `33064184773` attempt 2 on `93ec667ebf3768bb78f9622eb710681cba813698`                   |
| Decision            | Automated security gate `PASS`; independent/live sign-off `PENDING`                                 |

Release criterion is exactly zero unresolved Critical, High and Major findings. Lower-severity debt must be recorded with owner/rationale and may not conceal a higher-impact issue.
