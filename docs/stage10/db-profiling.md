# Stage 10 database profiling evidence

Measured on 2026-08-27 against the preserved PostgreSQL 18.6 database immediately after the
production-shaped 300-user acceptance run. The restored state contained 1,000 load users and
20,975 messages; `verify_load_state --require-k6-writes` passed before profiling.

The deterministic load seed completed an idempotent rerun in 16.432 seconds and produced:

| Entity                      |          Rows |
| --------------------------- | ------------: |
| Active load users           |         1,000 |
| Publications                |           120 |
| Comments / reactions        |     360 / 360 |
| Conversations               |            30 |
| Messages                    |        20,975 |
| Notifications               |        20,000 |
| Recipient snapshots / views | 8,220 / 4,120 |

`EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT JSON)` results from the warmed isolated database:

| Query                       | Root node      | Execution ms |
| --------------------------- | -------------- | -----------: |
| Feed                        | Sort           |        1.308 |
| Publication detail          | Sort           |        0.401 |
| Global search: publications | Sort           |        5.992 |
| Global search: comments     | Sort           |        3.273 |
| Global search: messages     | Sort           |       86.713 |
| Global search: files        | Sort           |        0.818 |
| Global search: employees    | Sort           |       24.550 |
| Messenger inbox             | Unique         |        0.299 |
| Message history             | Sort           |        1.397 |
| Unread                      | Sort           |        0.169 |
| Notification inbox          | Sort           |        0.226 |
| Analytics                   | GroupAggregate |      184.554 |

PostgreSQL reported `autovacuum=on`; the database size was 93,345,471 bytes. No index was added:
the post-load plans provide no evidence for a speculative Stage 10 index. HTTP and realtime
acceptance remains governed by the retained k6 summaries in [`evidence/`](evidence/).

Reproduce the seed and machine-readable summary:

```console
TANDEM_LOAD_PASSWORD='<operator supplied>' uv run python manage.py seed_load_profile \
  --confirm-load-environment
uv run python manage.py profile_database --username load-0001 \
  --query 'безопасность' --summary
```

Omit `--summary` to print the complete text plans.
