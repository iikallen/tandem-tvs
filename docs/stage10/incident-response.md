# Incident response runbook

## Severity and ownership

| Severity | Example | Response |
| --- | --- | --- |
| SEV-1 | PostgreSQL/data loss, broad authorization bypass, origin exposure, unavailable service | Page on-call immediately; freeze risky changes; incident commander and security/DB owner. |
| SEV-2 | Sustained >1% 5xx, p95 >2 s, stale outbox/fanout, media integrity failure | Page service owner; mitigate within the operational target. |
| SEV-3 | Optional email/push failure, isolated UX defect, capacity warning | Ticket and schedule; core News/Messenger remains available. |

Customer-specific contacts, paging targets and deadlines: `PENDING`.

Cloudflare Access can return its own login response while the origin connector is unavailable. If
the fault runner cannot use an approved Access service token, run it with `--skip-cloudflared` and
stop/recover `cloudflared` separately while an Access-authorized external browser continuously
probes `/api/v1/health/ready`. Record the external failure and recovery; an anonymous Access
redirect alone is not tunnel-outage evidence.

## First ten minutes

1. Open an incident record with UTC start, reporter, symptom and affected surface. Do not paste secrets/private content.
2. Confirm exact `/api/v1/runtime/meta` revision and whether a deployment is active.
3. Check public live/ready, protected `/internal/health`, alert graph and Compose service state.
4. Preserve sanitized logs/metrics; identify the durable boundary before restarting.
5. Stop deployments and destructive cleanup. If confidentiality/integrity is at risk, deny external traffic at Cloudflare Access while retaining forensic state.
6. Assign incident commander, communications and technical owner.

## Failure matrix

| Failure | Expected behavior | Recovery | Verify afterward |
| --- | --- | --- | --- |
| Redis | REST/search and DB sessions continue where supported; realtime/tasks degrade; durable work remains | Restart/replace Redis, then workers if needed | Outboxes catch up; no duplicate/lost committed messages/notifications; WSS reconnects. |
| Celery worker | Source/outbox rows accumulate | Restart targeted worker; do not delete queue rows | Oldest ages fall; schedules/fanout/delivery are idempotent. |
| Celery beat | Heartbeat stale; periodic reconciliation/cleanup not scheduled | Restart beat after broker/worker healthy | Heartbeat <60 s; due publications reconcile once. |
| Backend | Nginx returns errors while process unavailable | Restart backend image at exact SHA | Sessions follow designed expiry; committed state present; sockets reconnect/refetch. |
| Frontend/Nginx | SPA/API edge unavailable | Restart frontend; preserve backend/data | Headers, SPA, API proxy, protected media and WSS pass. |
| cloudflared | External path unavailable; origin services may remain healthy | Restart connector/check token/Cloudflare status | Access challenge, external HTTP and WSS pass; no origin bypass. |
| PostgreSQL | Ready fails; business operations unavailable | Recover DB/storage/connection capacity; restore only via approved plan | Migrations/state/media links/search/backlogs consistent. |
| Media read-only/full | Ready fails because required media is not writable | Stop uploads, recover disk/mount, do not delete unknown files | `verify_media_integrity`; authorized download/upload; backup current state. |
| SMTP/Web Push | Only optional external channel fails | Keep in-app source; repair configuration/provider and retry policy | No private payload leakage; pending delivery drains without duplicate visible events. |

## Security incident additions

For suspected IDOR, account compromise, secret leak, XSS or origin bypass:

- deny/contain before cleanup; preserve append-only auth/business audit and relevant proxy logs;
- rotate only affected secrets and invalidate sessions through supported security-epoch/session controls;
- never grant platform admin private-chat access for investigation; customer legal/regulatory procedure must authorize any exceptional data access, and that access must be technically limited and audited;
- verify media/search/notification exact-target authorization, not merely UI visibility;
- review whether logs/metrics/backups contain credentials, tokens, endpoints or message bodies;
- notify customer security/privacy owner according to their policy.

## Restart discipline

Restart only the identified component. Before restart, record backlog counts/oldest age and current SHA. After restart, compare counts, confirm no source-row loss and wait for backlog recovery. Do not use recursive volume deletion, database recreation, `flushall`, outbox truncation or blind image downgrade.

## Recovery acceptance

- exact expected SHA and healthy PostgreSQL/media;
- Redis/Celery state matches intended healthy/degraded mode;
- committed news/message/file survives;
- realtime and notifications catch up exactly once;
- sessions and permissions remain correct, including platform-admin private-chat denial;
- search returns authorized data;
- media integrity passes;
- alert resolves for the right reason, not because monitoring was disabled.

## Closeout

Record impact window, root cause, durable-data assessment, actions/owners, actual recovery times and follow-ups. Link sanitized evidence and change/rollback records. Restore silenced alerts, confirm backup schedule and run a targeted regression/fault test. Track corrective work through normal protected PR; do not patch containers by hand.
