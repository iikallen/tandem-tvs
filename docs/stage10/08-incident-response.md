# Stage 10 incident-response acceptance

Operator procedure: [`incident-response.md`](incident-response.md).

The release exercise must cover controlled failure and recovery of Redis, Celery worker, Celery beat, backend, frontend, cloudflared and PostgreSQL. After recovery: committed data survives, outboxes catch up, notifications/messages are not duplicated, sessions follow policy, media is consistent, search returns and realtime reconnects.

| Fault | Actual recovery result |
| --- | --- |
| Redis | `PENDING` |
| Celery worker | `PENDING` |
| Celery beat | `PENDING` |
| Backend | `PENDING` |
| Frontend | `PENDING` |
| cloudflared | `PENDING` |
| PostgreSQL | `PENDING` |
| Media read-only/full | `PENDING` |

Customer on-call contacts, severity response targets and communications policy remain `PENDING` until supplied by operations.
