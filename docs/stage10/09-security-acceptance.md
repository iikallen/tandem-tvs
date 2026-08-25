# Stage 10 security acceptance

Historical Stage 9 review reported zero unresolved Critical/High/Major findings for the Stage 9 scope. Stage 10 changes production configuration, deployment, backup and monitoring boundaries, so a new full-diff and whole-system review is mandatory. Its result is currently `PENDING`.

## Review matrix

| Area | Required control/evidence | Result |
| --- | --- | --- |
| Production settings bypass | `config.settings.production`; missing/unsafe values stop startup; `check --deploy` | `PENDING` |
| Development defaults | No development secret/password, demo admin/password, mock adapter, localhost/wildcard production origin | `PENDING` |
| Release identity | Semantic `APP_VERSION`, exact 40-hex SHA, immutable image labels/tags | `PENDING` |
| Host/proxy/origin | Allowed hosts/origins exact; trusted Cloudflare client IP only from tunnel subnet; direct origin blocked | `PENDING` |
| HTTPS/headers | Valid TLS, HSTS, nosniff, DENY frame, Permissions-Policy; CSP Report-Only browser audit before enforcement | `PENDING` |
| XSS/rich text | Structured allowlist, safe links/media node kinds, no `unsafe-eval`; no unexplained CSP violations | `PENDING` |
| CSRF/session | HttpOnly/Secure/SameSite session, CSRF on mutations, rotation, idle/absolute expiry, security-epoch invalidation | `PENDING` |
| Password/recovery | Argon2, generic denial, throttles, hash-only expiring one-use capabilities, no secret logs/URL query token | `PENDING` |
| WebSocket auth | Exact origin, one-use session-bound scoped ticket, epoch/expiry/socket limit, no private payload in Redis | `PENDING` |
| News/comment IDOR | Addressed queryset before detail/comment/reaction/ack/search/media | `PENDING` |
| Private-message IDOR | Membership intervals for inbox/history/context/search/reply/forward/file; Platform Admin has no bypass | `PENDING` |
| Channel permissions | Admin/writer/member mutation policy, bounded `@all`, membership changes audited | `PENDING` |
| Notification/search IDOR | Recipient-only notifications; every search section and destination independently reauthorize | `PENDING` |
| Media | Signature/type/size checks, non-executable/private response, safe storage path, rollback-safe file lifecycle | `PENDING` |
| Audit | Security/business/application logs separated; business/security audit append-only and previous/new state complete | `PENDING` |
| Backup permissions/secrets | `0700`/`umask 077`, separate mount, no URL output, safe manifest/tar, production restore refusal | `PENDING` |
| Metrics/log privacy | Monitoring bearer token; stable low-cardinality labels; no IDs, credentials, cookies, endpoints or bodies | `PENDING` |
| Outbox/retry exhaustion | Pending work never deleted by cleanup; bounded retry/alerts; duplicates blocked transactionally | `PENDING` |
| Disk full/read-only media | Ready fails; upload rollback preserves DB/file consistency; recovery and verifier documented | `PENDING` |
| DB pool exhaustion | Measured connection budget/headroom under 300-user and WSS profiles | `PENDING` |
| Load-test authorization | Seed/users/secrets isolated; load endpoints are normal authorized APIs; no production private-content capture | `PENDING` |
| Optional delivery | Internal SMTP; Web Push disabled without customer approval, generic payload and vendor allowlist | `PENDING` |
| Cloudflare bypass/HA claims | Access before origin; only Nginx on tunnel network; same-host connectors not described as host HA | `PENDING` |

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

## Sign-off

| Field | Value |
| --- | --- |
| Reviewer | `PENDING` |
| Reviewed commit | `PENDING` |
| Critical unresolved | `PENDING` |
| High unresolved | `PENDING` |
| Major unresolved | `PENDING` |
| Full gate rerun | `PENDING` |
| Decision | `PENDING` |

Release criterion is exactly zero unresolved Critical, High and Major findings. Lower-severity debt must be recorded with owner/rationale and may not conceal a higher-impact issue.
