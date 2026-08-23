# Stage 4 implementation plan

## Goal

Deliver the complete editorial workflow on top of the released Stage 3 foundation without
starting moderation, analytics, notifications, search, or messenger work.

## Release baseline

- Baseline commit: `12f0d3fd4f888784734691fb9865aeb6bb4729c5`.
- `stage-3-complete` is an immutable annotated tag for that commit.
- The clean Stage 3 production gate passed on GitHub Actions run `32642397810`.
- PostgreSQL Stage 2 acceptance, PostgreSQL/Redis Stage 3 acceptance, and all 17 live
  Playwright tests passed locally before this branch was created.

## Delivery slices

1. Extend the publication domain with lifecycle timestamps, optimistic revision, immutable
   versions, tags, pin slots, stable position-group audience rules, and reusable media assets.
2. Put every lifecycle transition behind one transactional service with row locking,
   permissions, validation, version capture, audit events, and automatic pin cleanup.
3. Add Celery worker and beat services. Reconcile scheduled and expired publications every
   15 seconds from PostgreSQL with `select_for_update(skip_locked=True)`.
4. Add editorial, pinning, taxonomy, versions, duplication, upload, and protected-media APIs.
5. Extend the rich-text contract with tables and internal media nodes that contain only asset
   identifiers; keep backend validation and frontend rendering aligned.
6. Build the editorial list, review queue, editor autosave/conflict flow, media library,
   taxonomy, version history, pin controls, and responsive/mobile states using UI Kit v2
   tokens and interaction patterns.
7. Add focused unit/API/security tests, real PostgreSQL/Celery/media acceptance, live
   Playwright coverage, Compose restart/persistence checks, and CI/release documentation.

## Verification sequence

1. Static checks, migration drift, backend tests and coverage.
2. Frontend format, lint, typecheck, unit tests, audit, and production build.
3. Clean Compose build and startup with PostgreSQL, three isolated Redis databases, backend,
   Celery worker, Celery beat, Nginx, and the shared media volume.
4. Stage 2, Stage 3, and Stage 4 acceptance scripts.
5. Live Playwright at 360, 390, 768, and 1440 pixels.
6. Restart recovery for backend, worker, beat, Redis, PostgreSQL, and media persistence.
7. External Cloudflare checks, including an authorized media response and an outsider 404.
8. Independent security/correctness review; no unresolved Critical or Major findings.
9. Final `make prod`, green CI, `STAGE4_REPORT.md`, merge to `main`, and immutable
   `stage-4-complete` tag.

