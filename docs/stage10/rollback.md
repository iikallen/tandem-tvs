# Rollback runbook

Rollback means returning to a known immutable release while preserving committed data. It is not `git pull` plus hope.

## Immediate triage

1. Stop new rollout actions; preserve current and previous SHA-tagged images.
2. Record exact current SHA, previous SHA, UTC time, failing checks and the pre-deploy backup.
3. Determine whether the release migration started/completed and whether it is backward-compatible.
4. If data integrity is uncertain, put the edge into maintenance/deny mode before changing containers.

## Decision tree

| Condition | Action |
| --- | --- |
| Failure before migration | Switch to previous immutable images. No database restore. |
| Migration did not change schema | Switch to previous immutable images. |
| Migration is explicitly backward-compatible with previous code | Switch images only, then smoke and monitor. Evidence for compatibility is required. |
| Migration is additive but previous code has not been tested against it | Treat as unknown; do not auto-rollback. Escalate to application/DB owners. |
| Destructive/incompatible migration or corrupted data | Automatic image rollback prohibited. Use approved isolated restore/recovery plan and change authorization. |
| PostgreSQL unavailable but data is intact | Recover PostgreSQL; do not restore merely to restart application processes. |
| Redis/worker/beat failure | Restart/recover only the affected disposable/worker layer and allow durable outboxes to catch up. |

No Stage 10 change should introduce a destructive migration. Still, verify rather than assume.

## Image-only rollback

Prepare a copy of the production env with `APP_GIT_SHA=<previous-40-character-sha>` and the matching `APP_VERSION`. Do not change database credentials or secrets as part of the rollback.

```sh
rollback_env=/run/secrets/tandem-rollback.env

docker image inspect "tandem-tvs-backend:<previous-sha>" >/dev/null
docker image inspect "tandem-tvs-frontend:<previous-sha>" >/dev/null

docker compose \
  --env-file "$rollback_env" \
  -f compose.yaml \
  -f compose.prod.yaml \
  up -d --no-build --wait backend celery-worker celery-beat frontend cloudflared
```

Do not rerun old migrations as a rollback mechanism. Confirm `/api/v1/runtime/meta` reports the previous exact SHA, then repeat health, auth, feed, Messenger, file, search, notification and WSS smoke from [`deployment.md`](deployment.md).

## Database/media restore path

A restore is a separate, destructive production recovery change, not an automatic application rollback. Before it:

- stop writes and preserve the failed database/media for investigation;
- identify business data created after the backup and obtain the required approval for its loss/replay;
- verify the selected backup manifest;
- prove the backup in an isolated database/media directory using [`backup-restore.md`](backup-restore.md);
- create a written cutover plan with application and database owners.

The provided `restore-drill.sh` deliberately refuses the production `DATABASE_URL`; it is not a one-command production overwrite tool.

## Post-rollback acceptance

- live/ready healthy; exact previous SHA visible;
- migrations table matches the code's supported schema;
- committed news/messages/files remain present;
- private-object authorization still holds;
- realtime/notification outboxes catch up without duplicates;
- search and notifications return after dependencies recover;
- media integrity reports zero failures;
- 5xx, p95 latency and backlog age return to baseline.

Keep incident/change notes, relevant sanitized logs, metrics interval, the failed SHA and the rollback SHA. Never copy secrets, session cookies, push endpoints or private content into the record.
