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

| Check                                                  | Result                                                                                             |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| Production Compose rendered with no development values | `PASS` — preflight and production-shaped deployment                                                |
| One-shot migrate observed before backend start         | `PASS` — production-shaped deployment                                                              |
| No public backend/PostgreSQL/Redis origin              | `PARTIAL` — exact-SHA local Compose published no origin ports; outside-network bypass test pending |
| Named tunnel `tandem-tvs` and Access                   | `PARTIAL` — anonymous Access challenge observed; named-tunnel and authorized-origin proof pending  |
| Redis degradation and durable recovery                 | `PASS` — exact-SHA local fault matrix                                                              |
| PostgreSQL/media readiness failure behavior            | `PASS` — fault/readiness and automated media tests                                                 |
| Exact runtime/image SHA                                | `PASS` — `2852bdb7c1500e85fe3b9785f1a4aaf77ad87f7e`                                                |

This file is an acceptance summary, not evidence by itself.
