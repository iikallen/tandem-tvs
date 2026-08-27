# Stage 10 capacity acceptance

Operational procedure and budget fields: [`capacity-plan.md`](capacity-plan.md).

Hard release profile:

- production-shaped data: up to 1 000 active users, about 120 publications and 20 000 messages with RU/KZ text;
- 180 portal/news/search + 90 Messenger HTTP + 30 realtime-active users for at least 30 minutes;
- separate 300 authenticated WebSocket connections for at least 15 minutes;
- HTTP error rate <1%; feed/detail/history/search p95 <2 s; realtime delivery p95 <1 s;
- zero application crashes, DB exhaustion, lost committed messages and authorization violations.

## Measured release record

| Metric                               | Actual                                                                                                                     |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| Dataset counts                       | 1 000 active load users; 120 publications; 360 comments/reactions; 30 conversations; 20 000 messages; 20 000 notifications |
| Duration and VU distribution         | 5m ramp + 30m hold; 180 portal + 90 Messenger HTTP + 30 realtime                                                           |
| HTTP errors                          | 0/44,960; 44,960/44,960 checks passed                                                                                      |
| Feed/detail p95                      | 581 / 576ms                                                                                                                |
| Inbox/history p95                    | History 749ms; post-run durable state PASS                                                                                 |
| Global search p95                    | 1.06s                                                                                                                      |
| Realtime p95                         | Message delivery 982ms; failures 0%                                                                                        |
| 300 WSS hold/reconnect               | Observed 303; completed 300; full-duration 300/300; failures 0%                                                            |
| Peak PostgreSQL connections / budget | Mixed 23/400; WSS 6/400; rollback/deadlock 0                                                                               |
| Redis/CPU/memory/disk peak           | WSS Redis container ~44.3MiB; post-run DB 93,345,471 bytes; representative media 8,252 bytes                               |
| Query-plan changes                   | Post-load PostgreSQL 18.6 plans captured; autovacuum on; no evidence-based index change (`db-profiling.md`)                |

Raw k6 summaries are retained in [`evidence/`](evidence/). Customer host/storage capacity and alert
limits remain operational decisions; they are not inferred from the representative fixture size.
