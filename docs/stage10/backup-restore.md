# Backup and restore runbook

Required policy from the TZ: PostgreSQL and protected files daily, retained at least 14 days, with a proven restore. The repository supplies application-aware tooling; scheduling, the separate corporate mount, encryption/access control and off-host copies belong to operations.

Current acceptance state: backup tool `PENDING`, full isolated restore drill `PENDING`, production daily schedule `PENDING`.

## Safety invariants

- `BACKUP_ROOT` is a dedicated corporate backup mount, not the PostgreSQL or media volume and not nested inside either path.
- Backup directory permissions are `0700`; created files inherit `umask 077`.
- The PostgreSQL URL comes from the secret store and is never printed.
- A complete backup contains `database.dump`, `media.tar`, `source-evidence.txt`, `SHA256SUMS` and `created-at.txt`.
- A backup is not accepted until checksum verification and an isolated restore succeed.
- `backup.sh` serializes runs and holds the application's PostgreSQL advisory write lock across both archives. Normal HTTP writes return `503` while the lock is held; do not run media-mutating management commands during the backup window.
- `restore-drill.sh` compares the actual source/target server and database identity, requires `RESTORE_CONFIRMATION=isolated-database`, a fresh database with no user objects and an empty media target. It never runs `pg_restore --clean`.
- Orphan media is reported, never automatically deleted.

## Daily backup

Run where `pg_dump`, POSIX tar, Python 3 and the live media mount are available. Verify the backup mount is a different filesystem/storage target:

```sh
findmnt -T /srv/tandem-media
findmnt -T /srv/tandem-backups
```

The `SOURCE` values must differ. A different directory on the same application disk does not meet the operational intent.

```sh
export DATABASE_URL='<from-secret-store>'
export POSTGRES_DATA_ROOT='/var/lib/postgresql/data' # mounted read-only is sufficient
export MEDIA_ROOT='/srv/tandem-media'
export BACKUP_ROOT='/srv/tandem-backups'

./ops/backup/backup.sh
```

Do not enable shell tracing. Capture only the final backup directory and exit status. The script writes into a private temporary directory and atomically renames it only after dump, tar and manifest creation succeed.

Verify the newest backup without restoring:

```sh
python3 ops/backup/verify_manifest.py verify /srv/tandem-backups/<UTC-directory>
pg_restore --list /srv/tandem-backups/<UTC-directory>/database.dump >/dev/null
tar -tf /srv/tandem-backups/<UTC-directory>/media.tar >/dev/null
```

The manifest verifier also rejects unsafe tar members and missing/inconsistent source evidence. `source-evidence.txt` records the canonical database identity plus resolved PostgreSQL, media and backup mount/device markers; the script fails unless the backup target is outside both source failure domains. Treat any checksum/archive error as a failed backup and alert; do not delete the previous good copy.

## Scheduling and retention

Use the customer's scheduler/backup platform, not Celery, because backups must continue when the application is unhealthy. Minimum policy:

- create once every UTC day;
- alert on missing/failed job;
- retain at least the newest 14 daily successful sets;
- prevent application service accounts from deleting historical backups;
- encrypt the corporate backup target according to customer policy;
- periodically copy off-host/off-disk if the required disaster domain includes host/disk loss.

Delete an expired backup set only after a newer set has passed the isolated restore schedule. The repository deliberately does not provide an automatic `rm` retention script; storage lifecycle belongs to the corporate backup system with audit and legal policy.

## Isolated restore drill

Provision a fresh, non-production PostgreSQL database and an empty media directory. Keep the production `DATABASE_URL` available for the canonical identity guard. The restore identity may create objects in that isolated database only; the drill refuses any existing user object rather than cleaning it.

```sh
export BACKUP_DIR='/srv/tandem-backups/<UTC-directory>'
export RESTORE_DATABASE_URL='postgresql://<isolated-user>:<secret>@<isolated-host>/<fresh-db>'
export RESTORE_MEDIA_ROOT='/srv/tandem-restore/media'
export RESTORE_MEDIA_OWNER='10001:10001' # backend image app uid:gid
export RESTORE_CONFIRMATION='isolated-database'

cd backend
../ops/backup/restore-drill.sh
```

The command verifies `SHA256SUMS`, restores PostgreSQL with `--exit-on-error`, extracts the safe media archive, assigns it to the non-root backend uid/gid and runs `manage.py verify_restored_state`. Omit `RESTORE_MEDIA_OWNER` only when the restore command already runs as the backend filesystem owner. It must finish with `Restore drill: PASS`.

Start the application against the restored DB/media and use isolated credentials/hostname. Validate:

1. Login with an active test account; inactive account remains denied.
2. Addressed news and one mandatory acknowledgement are present.
3. Direct/group/channel conversations, message history and read state are present.
4. Protected files open only for authorized users.
5. RU/KZ search returns expected authorized results.
6. Notification inbox/read state is present.
7. `python manage.py verify_media_integrity` returns zero missing, size, SHA-256 and orphan failures.

Record backup timestamp, backup size, restore start/end UTC, database/media targets, verification counts and result. Never record credentials or private content. Destroy the isolated environment only after evidence is retained.

## Production recovery

The drill tooling is intentionally not a production overwrite procedure. A production restore requires an approved incident/change plan, stopped writes, preservation of current failed data, an explicit data-loss/replay decision and an already-proven backup. See [`rollback.md`](rollback.md).

## PITR option

The TZ defines no RPO shorter than one day. Logical DB+media backup is mandatory; PostgreSQL base backup plus continuous WAL archive/PITR is an optional customer policy for a smaller RPO. Enabling it also requires a coordinated media recovery point and routine PITR drills. Do not claim PITR until archive, restore command, retention and measured drill evidence exist.

## Acceptance record

| Check | Actual result |
| --- | --- |
| Backup directory / UTC | `PENDING` |
| DB dump size / media tar size | `PENDING` |
| SHA-256 verification | `PENDING` |
| Fresh isolated DB/media | `PENDING` |
| Restore duration | `PENDING` |
| Restored-state verifier | `PENDING` |
| Login/news/Messenger/files/search/notifications | `PENDING` |
| Media integrity | `PENDING` |
| Daily scheduler and >=14-day retention | `PENDING` |

Only actual operator evidence may replace `PENDING`.
