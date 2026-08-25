# Stage 10 database profiling evidence

Measured on 2026-08-25 against an isolated PostgreSQL 18.6 database created from all current
migrations. This is query-plan evidence, not the 300-user acceptance result.

The deterministic load seed completed an idempotent rerun in 16.432 seconds and produced:

| Entity | Rows |
| --- | ---: |
| Active load users | 1,000 |
| Publications | 120 |
| Comments / reactions | 360 / 360 |
| Conversations | 30 |
| Messages | 20,000 |
| Notifications | 20,000 |
| Recipient snapshots / views | 8,220 / 4,120 |

`EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT JSON)` results from the warmed isolated database:

| Query | Root node | Execution ms | Shared hits | Shared reads |
| --- | --- | ---: | ---: | ---: |
| Feed | Sort | 1.640 | 260 | 0 |
| Publication detail | Sort | 0.555 | 11 | 0 |
| Global search: publications | Sort | 11.411 | 288 | 0 |
| Global search: comments | Sort | 10.918 | 292 | 0 |
| Global search: messages | Sort | 89.828 | 14,688 | 0 |
| Global search: files | Sort | 0.838 | 1 | 0 |
| Global search: employees | Sort | 28.437 | 173 | 0 |
| Messenger inbox | Unique | 0.385 | 16 | 0 |
| Message history | Sort | 1.471 | 669 | 0 |
| Unread | Sort | 0.149 | 7 | 0 |
| Notification inbox | Sort | 0.421 | 22 | 0 |
| Analytics | Aggregate | 314.325 | 549 | 0 |

PostgreSQL reported `autovacuum=on`. No index was added: the measured plans provide no evidence
for a speculative Stage 10 index. HTTP and realtime acceptance remains governed by the k6 p95
thresholds on the production-shaped environment.

Reproduce the seed and machine-readable summary:

```console
TANDEM_LOAD_PASSWORD='<operator supplied>' uv run python manage.py seed_load_profile \
  --confirm-load-environment
uv run python manage.py profile_database --username load-0001 \
  --query 'безопасность' --summary
```

Omit `--summary` to print the complete text plans.
