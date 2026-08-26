# Capacity plan

Design envelope from the TZ: up to 1 000 employees, 300 concurrent sessions, 50-150 publications/month, up to 20 000 messages/day and about 100 GB/year of media. Numbers below distinguish current configuration from evidence still required.

## Acceptance workload

| Scenario | Required profile | Threshold | Actual |
| --- | --- | --- | --- |
| Portal/news/search | 180 constant VUs, part of 30-minute run | Error rate <1%; feed/detail/search p95 <2 s | `PENDING` |
| Messenger HTTP | 90 constant VUs, part of 30-minute run | History/inbox p95 <2 s; no lost commit | `PENDING` |
| Realtime-active users | 30 constant VUs, part of 30-minute run | Healthy delivery p95 <1 s | `PENDING` |
| Authenticated WebSockets | 300 sockets held at least 15 minutes | No crash/leak/DB exhaustion; reconnect works | `PENDING` |
| Dataset | Up to 1 000 active users, ~120 publications, ~20 000 messages, RU/KZ text and representative small files | Deterministic/idempotent seed | 1 000 users, 120 publications, 20 000 messages and 20 000 notifications; idempotent rerun 16.432 s |

CI runs only a 5-10 VU, 1-2 minute smoke. It cannot substitute for either dedicated profile.

## PostgreSQL connection budget

Measure the target instance, do not assume image defaults:

```sql
SHOW max_connections;
SHOW superuser_reserved_connections;
SHOW autovacuum;

SELECT application_name, state, count(*)
FROM pg_stat_activity
GROUP BY application_name, state
ORDER BY application_name, state;
```

Record the release values:

| Budget item | Value |
| --- | ---: |
| `max_connections` | 400 |
| PostgreSQL reserved connections | 3 |
| Maximum backend connections across all replicas | 320 |
| Celery worker connection budget | 4 |
| Migration job | 1 active connection during deployment |
| DBA/monitoring/backup/restore reserve | 30 |
| Unallocated surge headroom | 42 |
| Allocated total including reserved connections | 400 |

Required equation:

```text
backend + Celery + migration + monitoring/backup + DBA reserve + surge headroom
<= max_connections - PostgreSQL reserved connections
```

Django production uses `CONN_MAX_AGE=0`, six Uvicorn workers and Celery concurrency 2. On the clean deterministic 300-user profile, six workers reduced realtime message delivery p95 from 1.59 s with four workers to 909.49 ms. Eight workers measured 910.20 ms, so six is the smallest configuration that meets the objective without redundant processes. The load harness chooses an eligible conversation deterministically by UUID/VU instead of repeatedly concentrating traffic in whichever conversation a previous run made hottest. Record `pg_stat_activity`, CPU saturation and p95 during each release acceptance run.

## Query profiling

After seeding and during/after load, capture `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` for feed, publication detail, global search, conversation inbox, message history, unread, notification inbox and analytics. Store sanitized plans without user content. Add/remove indexes only from measured evidence. The current isolated PostgreSQL 18.6 measurements are recorded in [`db-profiling.md`](db-profiling.md); they are query execution plans, not HTTP p95 load results.

Verify `autovacuum=on`, table dead tuples and analyze timestamps. Routine maintenance uses autovacuum plus ordinary `VACUUM (ANALYZE)` where evidence requires it; never schedule `VACUUM FULL` as routine work.

| Query family | Measured isolated query execution | Index change |
| --- | --- | --- |
| Feed/detail | 1.640 / 0.555 ms | None |
| Global search sections | publications 11.411; comments 10.918; messages 89.828; files 0.838; employees 28.437 ms | None |
| Inbox/history/unread | 0.385 / 1.471 / 0.149 ms | None |
| Notifications | 0.421 ms | None |
| Analytics | 314.325 ms | None |

## Redis and realtime

Redis uses separate logical DBs for cache, realtime and Celery. Record `maxmemory`, eviction policy, steady/peak used memory, connected clients and blocked clients during both profiles. Required release values are `PENDING`.

At 300 sockets, track application lease count, Redis clients/memory, backend CPU/memory, reconnect rate and DB connections. Realtime payloads are identifier hints; message bodies remain in PostgreSQL. If a single-host connector/process fails, clients reconnect and REST resynchronizes.

## Storage budget

| Store | Planning input | Required capacity decision |
| --- | --- | --- |
| Media | ~100 GB/year plus temporary upload/headroom | Customer retention horizon x growth + operating headroom; `PENDING`. |
| PostgreSQL | 20 000 messages/day peak plus reads/audit/search indexes | Measure seeded DB and growth/day; `PENDING`. |
| Backup | DB dump + full media set x >=14 daily copies unless deduplicated by corporate platform | Backup-platform sizing; `PENDING`. |
| Host filesystem | Images, logs, temp files and safety margin | Infrastructure monitoring threshold; `PENDING`. |

Do not generate 100 GB binary data for CI. Use small real representative files for correctness and separately validate storage quotas, disk-full behavior and backup throughput.

## Scale decision rules

- Scale/tune only after a repeatable failing threshold and resource evidence.
- Adding backend replicas does not change the one-shot migration boundary.
- More `cloudflared` connectors on one host do not provide host HA.
- Host HA needs a second failure domain, load routing, shared/replicated media and explicit PostgreSQL HA/failover.
- The 99% availability SLO starts after go-live monitoring; it is not inferred from the load duration.

This plan becomes release evidence only when every `PENDING` measurement is copied from the actual production-shaped run into `STAGE10_REPORT.md`.
