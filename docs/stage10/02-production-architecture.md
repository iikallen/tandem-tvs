# Stage 10 production architecture acceptance

The current architecture is maintained in [`../architecture.md`](../architecture.md). It supersedes the obsolete Stage 1 passwordless/portal-auth description and records the actual local-auth, News, Messenger, Notifications, Search and operations system.

Release-significant decisions:

- PostgreSQL is the business source of truth; protected media is the binary source of truth.
- Redis is disposable cache/realtime/broker infrastructure, never the only copy of a committed mutation.
- Production authentication is `LOCAL_ONLY`; the Stage 6 amendment replaced portal SSO. `PortalAdapter` is an optional directory boundary and is `unavailable` in production.
- Cloudflare Access/Tunnel -> Nginx is the only external path. Django, PostgreSQL and Redis have no Internet listener.
- Production Compose has explicit required values and immutable SHA-tagged images.
- Migrations are a one-shot service; backend replicas never migrate on entrypoint.
- Durable outbox/audit rows commit with source mutations; delivery is post-commit and idempotent.
- Platform Admin manages accounts but is not a private-chat reader.
- Public readiness depends on PostgreSQL and writable media. Redis failure is degraded and alerted.
- Backup covers DB+media on a separate corporate mount; restore is proven only in an isolated target.

## Acceptance

| Check | Result |
| --- | --- |
| Production Compose rendered with no development values | `PENDING` |
| One-shot migrate observed before backend start | `PENDING` |
| No public backend/PostgreSQL/Redis origin | `PENDING` |
| Named tunnel `tandem-tvs` and Access | `PENDING` |
| Redis degradation and durable recovery | `PENDING` |
| PostgreSQL/media readiness failure behavior | `PENDING` |
| Exact runtime/image SHA | `PENDING` |

This file is an acceptance summary, not evidence by itself.
