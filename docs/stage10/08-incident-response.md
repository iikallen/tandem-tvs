# Stage 10 incident-response acceptance

Operator procedure: [`incident-response.md`](incident-response.md).

The release exercise must cover controlled failure and recovery of Redis, Celery worker, Celery beat, backend, frontend, cloudflared and PostgreSQL. After recovery: committed data survives, outboxes catch up, notifications/messages are not duplicated, sessions follow policy, media is consistent, search returns and realtime reconnects.

| Fault                | Actual recovery result                                                                                                                                         |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Redis                | `PASS` — readiness remained available; committed probe reconciled exactly once; session/realtime/media/search passed after recovery.                           |
| Celery worker        | `PASS` — queued fanout/outbox work caught up without duplicate message or recipient notification.                                                              |
| Celery beat          | `PASS` — heartbeat became observably stale, then recovered; runtime/data checks passed.                                                                        |
| Backend              | `PASS` — process stopped, recovered healthy, durable session/data/media/search/realtime checks passed.                                                         |
| Frontend             | `PASS` — nginx stopped, recovered healthy and the full runtime verification passed.                                                                            |
| cloudflared          | `PENDING` — requires an Access-authorized external probe; it was explicitly skipped locally.                                                                   |
| PostgreSQL           | `PASS` — readiness changed to 503 while stopped; source digests, session, media, search and realtime passed after recovery.                                    |
| Media read-only/full | `PASS` — automated rollback/full-disk behavior passed; live read-only volume produced readiness 503, then recovered to readiness 200 and media-integrity PASS. |

Customer on-call contacts, severity response targets and communications policy remain `PENDING` until supplied by operations.
