# Stage 10 backup/restore acceptance

Operator procedure: [`backup-restore.md`](backup-restore.md).

Required outcome: a restrictive daily backup of PostgreSQL and protected media on a separate corporate mount, retained at least 14 days, with SHA-256 verification and a successful restore into a fresh isolated database/media target. Login, News, Messenger, files, search, notifications and media integrity must work after restore.

| Evidence | Actual |
| --- | --- |
| Backup UTC directory and sizes | `PENDING` |
| Corporate mount separate from data volumes | `PENDING` |
| Manifest/archive/source-failure-domain verification | `PENDING` |
| Fresh isolated restore target | `PENDING` |
| Restore duration and verifier output | `PENDING` |
| Product smoke after restore | `PENDING` |
| Daily scheduler and >=14 successful retained days | `PENDING` |

PITR is optional until the customer defines a smaller RPO. It must never be claimed merely because PostgreSQL supports WAL archiving.
