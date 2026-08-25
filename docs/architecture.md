# Tandem TVS production architecture

Status: Stage 10 release candidate architecture.
Last reviewed: 2026-08-25

## System context

```text
                         Browser
                            |
                  Cloudflare Access policy
                            |
                   named Cloudflare Tunnel
                            |
                            v
                    Nginx / React SPA
                            |
                  /api + /ws + /media
                            |
                            v
                Django ASGI / DRF / Channels
                  |           |           |
                  v           v           v
             PostgreSQL     Redis      Media volume
                  |           |
                  |        cache / channel layer /
                  |        Celery broker and result
                  |
                  +---- Celery worker / beat
```

Cloudflare is the selected external edge, not an identity provider for Tandem. Production authentication is local (`LOCAL_ONLY`) with Argon2 credentials, HttpOnly database sessions and CSRF protection. This intentionally supersedes the original portal-only SSO requirement under the approved Stage 6 amendment.

## Sources of truth

| Data | Authority | Failure behavior |
| --- | --- | --- |
| Accounts, active state, credentials, grants and sessions | PostgreSQL | PostgreSQL failure makes the application not ready. |
| News, comments, audit, Messenger, notifications and search source rows | PostgreSQL | Committed rows survive process/Redis restart. |
| Protected binary content | Media volume, linked from PostgreSQL | Unwritable required media makes readiness fail; integrity is checked separately. |
| Cache, WebSocket fanout and task transport | Redis | Disposable acceleration/infrastructure; outage is degraded, durable outboxes retry. |
| Optional directory profile/org data | `PortalAdapter` import boundary | Production `unavailable` adapter fails closed and cannot modify local security state. |
| Release identity | `APP_VERSION` + exact 40-character `APP_GIT_SHA` | Returned as safe runtime metadata and embedded in image labels. |

Redis is never the business durability boundary. A realtime event carries identifiers/version hints, not private message content; clients refetch authorized REST state.

## Runtime components

### Frontend and edge

Nginx serves the immutable Vite build and proxies HTTP/WebSocket traffic to Django. It applies HSTS, clickjacking, MIME, referrer and permissions headers. CSP is enforced after the full browser suite and external responsive sweep reported no unexplained violations. The named Cloudflare tunnel makes outbound connections; no database, Redis or Django host port is an Internet origin.

Two `cloudflared` connectors on one host improve connector-process tolerance only. Host-level availability requires another physical host and a separate PostgreSQL/media HA design; this repository does not claim host-level HA.

### Django applications

- `identity`: local accounts, Argon2/session authentication, recovery, invitations, `AccessGrant`, security events, optional directory import.
- `organization`: active org units and position groups used by audiences and people search.
- `publications`: news, taxonomy, audiences, versions, pins, media, acknowledgements, analytics and append-only editorial audit.
- `discussions`: threaded comments, mentions, reactions, reports, restrictions, stop words and publication realtime hints.
- `messenger`: direct/group/channel conversations, interval memberships, messages, receipts, attachments, reactions, pins, forwarding and search.
- `notifications`: durable fanout, grouping, preferences, in-app state, generic Web Push, internal SMTP delivery and notification sockets.
- `search`: authorization-first PostgreSQL search across publications, comments, messages, files and employees with separate RU/KZ configurations.
- `realtime`: one-use session-bound tickets, socket leases/security invalidation and durable outbox delivery.
- `ops`: detailed health, low-cardinality metrics, bounded operational cleanup, media integrity and restored-state verification.
- `core`: public liveness/readiness and safe runtime metadata.

### Background processing

Celery worker executes schedule reconciliation, realtime outbox, notification fanout/delivery and bounded cleanup. Beat schedules recurring reconciliation and cleanup. Durable work state lives in PostgreSQL; Redis broker loss delays work but must not delete committed source data.

Migrations do not run in the application entrypoint. Production Compose starts a one-shot `migrate` service after PostgreSQL is healthy; backend starts only after that job exits successfully. This avoids concurrent migration attempts when backend replicas are later introduced.

## Trust boundaries

1. **Internet -> Cloudflare Access/Tunnel.** Cloudflare Access is the external admission policy; TLS is terminated at the managed edge.
2. **Tunnel -> Nginx.** Only Nginx joins the tunnel edge network. Forwarded metadata is trusted only from this topology.
3. **Nginx -> Django.** Nginx exposes application routes, protected media proxy responses and WebSocket upgrade; Django owns authorization.
4. **Django -> PostgreSQL/media.** These are the durable business and binary boundaries. Backups cover both and go to a separate corporate mount.
5. **Django/Celery/Channels -> Redis.** Redis contains disposable transport/acceleration state; URLs and queue contents are never public health detail.
6. **Optional outbound delivery.** SMTP must be internal/configured. Standards Web Push necessarily contacts browser vendors, so it stays disabled until explicit customer security approval; payloads are generic wake-ups.

## Authorization model

Access consists of authentication, module grant and object membership/audience. A hidden React button is never an authorization control.

- `PLATFORM/ADMIN` manages accounts/grants but does not imply NEWS or MESSENGER membership.
- NEWS roles are MEMBER, AUTHOR, EDITOR, MODERATOR and ADMIN.
- MESSENGER grants allow entry; conversation membership intervals determine content visibility.
- Channel membership roles ADMIN/WRITER/MEMBER determine channel mutations.
- Publication feed/detail/comments/media/search begin from `visible_to(user)` or the equivalent scoped queryset.
- A known UUID never grants access. Non-members receive a denial/hidden-object response consistently.
- Platform administrators cannot read private chats unless they are normal members of that conversation.

The exhaustive mapping is in [`stage10/permissions-matrix.md`](stage10/permissions-matrix.md).

## Data and transaction boundaries

- PostgreSQL transactions commit business mutation and outbox/audit rows together.
- Realtime/notification delivery happens after commit and is idempotent.
- Message client IDs and database constraints prevent duplicate committed messages on retry.
- Media upload removes an already-written file when its database transaction fails. Media deletion commits the database/audit change first and removes the file in `transaction.on_commit()`.
- Protected files are returned only after reauthorizing their current parent publication/comment/message visibility.
- Editorial, moderation, security and Messenger audit trails are append-only through the application.

## Health and observability

| Endpoint | Audience | Meaning |
| --- | --- | --- |
| `/api/v1/health/live` | public | Process responds; no dependency claim. |
| `/api/v1/health/ready` | public | PostgreSQL and required media usable. Redis outage is degraded, not false readiness failure. |
| `/internal/health` | monitoring token | Named dependency status without credentials, hostnames or queue payloads. |
| `/internal/metrics` | monitoring token | Low-cardinality Prometheus text exposition. |
| `/api/v1/runtime/meta` | public safe metadata | Version/revision and non-secret runtime capabilities. |

Metrics label only method, route name and status code; never user, conversation, message or publication IDs. Security events, business audit and application logs remain distinct records with distinct purposes.

## Deployment and recovery

Development uses `compose.yaml` plus `compose.local.yaml`. Production always overlays `compose.prod.yaml`; required-variable syntax and Django production checks reject missing/known-development secrets, weak DB credentials, localhost/wildcard origins, mock portal adapter, bootstrap admin and invalid release metadata.

Images are built/tagged by exact Git SHA. A deployment follows: preflight -> backup -> immutable build -> one-shot migrate -> start -> health -> functional smoke -> backlog/metrics acceptance. Rollback reuses the previous immutable images only when schema compatibility allows it; destructive migration rollback requires the isolated restore procedure.

Backups contain PostgreSQL custom-format dump plus protected media tar and SHA-256 manifest on an operator-supplied mount that is outside both data volumes. Restore is allowed only into an explicitly confirmed isolated database and empty media directory, followed by state/media verification. PITR/WAL archiving is an optional customer RPO decision, not silently claimed by this repository.

See [`stage10/deployment.md`](stage10/deployment.md), [`stage10/rollback.md`](stage10/rollback.md) and [`stage10/backup-restore.md`](stage10/backup-restore.md).

## Capacity and availability boundary

The original design envelope is 1 000 users, 300 concurrent sessions, about 20 000 peak messages/day and about 100 GB media growth/year. Stage 10 acceptance requires a 300-session 30-minute k6 profile and a separate 300-authenticated-WebSocket 15-minute profile. Worker counts and connection budgets are changed only from those measurements.

The 99% availability target is a post-go-live SLO. Stage 10 can prove monitoring, alerting, recovery controls, soak/fault behavior and the start of measurement; a short release test cannot honestly prove a long observation period.

## Release boundary

Stage reports 1-9 are historical evidence and are not rewritten. `stage-10-complete` is created only from a protected-main merge commit whose exact post-merge release gate is green and whose acceptance report contains actual results. `v1.0.0` requires separate formal customer acceptance. No Stage 11 is implied by this architecture.
