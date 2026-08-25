# Stage 10 rollback acceptance

Procedure: [`rollback.md`](rollback.md).

Release acceptance requires:

- previous backend/frontend SHA-tagged images remain available;
- operator can identify whether migration is absent, compatible or destructive before rollback;
- image-only rollback never runs old migrations or restores a database;
- destructive/unknown schema rollback stops for approval and uses a separately proven restore plan;
- post-rollback health, exact SHA, data, permissions, outbox catch-up, search and media checks are explicit.

| Exercise | Actual |
| --- | --- |
| Previous image availability | `PENDING` |
| Schema compatibility decision | `PENDING` |
| Non-destructive rollback rehearsal | `PENDING` |
| Post-rollback product/permission smoke | `PENDING` |
| Recovery time | `PENDING` |

The runbook is not itself proof that rollback works.
