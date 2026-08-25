# Stage 10 capacity acceptance

Operational procedure and budget fields: [`capacity-plan.md`](capacity-plan.md).

Hard release profile:

- production-shaped data: up to 1 000 active users, about 120 publications and 20 000 messages with RU/KZ text;
- 180 portal/news/search + 90 Messenger HTTP + 30 realtime-active users for at least 30 minutes;
- separate 300 authenticated WebSocket connections for at least 15 minutes;
- HTTP error rate <1%; feed/detail/history/search p95 <2 s; realtime delivery p95 <1 s;
- zero application crashes, DB exhaustion, lost committed messages and authorization violations.

## Measured release record

| Metric | Actual |
| --- | --- |
| Dataset counts | 1 000 active load users; 120 publications; 360 comments/reactions; 30 conversations; 20 000 messages; 20 000 notifications |
| Duration and VU distribution | `PENDING` |
| HTTP errors | `PENDING` |
| Feed/detail p95 | `PENDING` |
| Inbox/history p95 | `PENDING` |
| Global search p95 | `PENDING` |
| Realtime p95 | `PENDING` |
| 300 WSS hold/reconnect | `PENDING` |
| Peak PostgreSQL connections / budget | `PENDING` |
| Redis/CPU/memory/disk peak | `PENDING` |
| Query-plan changes | Isolated PostgreSQL 18.6 plans captured; autovacuum on; no evidence-based index change (`db-profiling.md`) |

No threshold is passed until the dedicated production-shaped run supplies the actual output.
