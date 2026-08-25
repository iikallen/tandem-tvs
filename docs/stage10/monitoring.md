# Monitoring and alerting runbook

Monitoring must answer: is the service reachable, can it use durable storage, are users seeing errors/latency, and are durable delivery backlogs catching up? It must not expose private content or high-cardinality identifiers.

## Endpoints

| Endpoint | Authentication | Use |
| --- | --- | --- |
| `/api/v1/health/live` | Public | Process liveness only. |
| `/api/v1/health/ready` | Public | PostgreSQL and writable required media; Redis outage is reported degraded but does not make DB-backed REST unavailable. |
| `/internal/health` | `Authorization: Bearer <OPS_MONITORING_TOKEN>` | Dependency names/status only. |
| `/internal/metrics` | Same token | Prometheus text exposition. |
| `/api/v1/runtime/meta` | Public safe response | Confirm version and exact deployed revision. |

Keep the ops token in the secret store and Prometheus authorization configuration. Do not place it in a URL, repository or dashboard variable visible to ordinary users. Prefer scraping on the internal/admin path; if requests traverse Cloudflare, add a least-privilege service-token policy as a separate control.

## Metrics contract

| Metric | Meaning |
| --- | --- |
| `tandem_http_requests_total{method,route,status}` | Django responses; `route` is the stable URL name, not raw UUID path. |
| `tandem_http_request_duration_seconds` | Histogram by method and stable route. |
| `tandem_postgres_up`, `tandem_redis_up`, `tandem_media_up` | Dependency probes. |
| `tandem_active_realtime_sockets` | Active lease count. |
| `tandem_realtime_outbox_pending`, `...oldest_seconds` | Durable realtime delivery backlog. |
| `tandem_notification_fanout_pending`, `...oldest_seconds` | Durable notification fanout backlog. |
| `tandem_notification_delivery_pending` | Pending external-delivery attempts. |
| `tandem_celery_heartbeat_age_seconds` | Reconciliation heartbeat age; `-1` means absent. |
| `tandem_media_integrity_failures` | Last media verifier failure count. |

Forbidden labels/payloads: user, message, conversation, publication, notification or file IDs; username/email/IP; message/comment text; filenames; passwords; cookies/CSRF/session tokens; VAPID keys/subscription endpoints; database/Redis URLs. Application logs, authentication security events and business audit are separate sources and must not be merged into a mutable audit substitute.

## Alerts

Authoritative rules: `ops/prometheus/alerts.yml`.

| Alert | Current threshold | First response |
| --- | --- | --- |
| `TandemHighHttpErrorRate` | 5xx >1% for 5 min | Identify stable routes and release SHA; check PostgreSQL/media/deploy. |
| `TandemHighEndpointLatency` | p95 >2 s for 10 min | Compare endpoint/load, DB plans/connections and host saturation. |
| `TandemRealtimeBacklog` | oldest >30 s for 5 min | Check Redis, worker and outbox retries. |
| `TandemNotificationBacklog` | oldest >60 s for 5 min | Check worker/fanout failure and preference-delivery errors. |
| `TandemCeleryHeartbeatMissing` | absent/>60 s for 2 min | Check beat, worker, broker and reconciliation logs. |
| `TandemPostgresUnavailable` | down for 1 min | Treat as critical; stop unsafe deploys/writes and recover DB. |
| `TandemRedisUnavailable` | down for 2 min | Degraded realtime/background state; DB REST may continue. |
| `TandemMediaIntegrityFailure` | storage down or failures >0 for 1 min | Freeze media mutations if needed; inspect filesystem and latest backup. |

Route, on-call receiver, notification channel and maintenance silences are customer configuration. Test every rule against a non-production Prometheus before release; current firing/routing evidence is `PENDING`.

## Dashboard minimum

- deployed `version`/`revision` annotation;
- request rate, 5xx ratio and p50/p95/p99 by stable route;
- readiness and PostgreSQL/Redis/media state;
- active sockets;
- realtime and notification pending count/oldest age;
- Celery heartbeat age and external delivery pending;
- media verifier timestamp/failure count;
- host CPU/memory/disk/inode and PostgreSQL connections from infrastructure exporters.

The application intentionally does not implement host/PostgreSQL exporters. Reuse the customer's monitoring platform.

## Routine operator checks

Daily: alert state, backup job, PostgreSQL/media capacity, oldest backlogs, heartbeat and media verifier. Weekly: trend p95/error rate/storage growth and review disabled/failed delivery causes. Monthly: isolated restore drill according to customer policy, fault exercise, access review for platform/admin/monitoring credentials and SLO report.

## 99% availability SLO

Availability is measured after go-live over the customer-approved observation window:

```text
availability = successful eligible requests / all eligible requests
```

Define eligible routes, planned maintenance, synthetic frequency and error-budget owner before the clock starts. Stage 10 proves the controls and starts measurement; it must not label a short soak as `99% PASS`.

## Diagnostic order

1. Confirm exact release SHA and public live/ready.
2. Read detailed health and metrics with the ops token.
3. Check Compose `ps` and bounded logs for the failing service.
4. Check PostgreSQL connections/locks/disk, media disk/inodes, Redis, worker and beat.
5. Check durable outbox/fanout ages before restarting anything.
6. Follow [`incident-response.md`](incident-response.md); use rollback only after the schema/data decision.

Never use `docker compose down -v`, clear outbox tables, delete media or flush Redis as a generic diagnostic step.
