# Stage 4 decisions

## Domain and concurrency

- `Publication.status` is the authoritative lifecycle state. Only the lifecycle service may
  change it or its transition timestamps.
- Every write receives `expected_revision`. A transactional row lock compares it with
  `edit_revision`; stale writes return HTTP 409 and never overwrite newer content.
- Regular saves increment `edit_revision`. Autosave is debounced in the browser and records
  at most one immutable version per actor and publication per minute.
- `PublicationVersion` is append-only at the model and queryset layers. Its canonical JSON
  snapshot and SHA-256 content hash make tampering detectable.

## Scheduling

- PostgreSQL is the sole source of truth for `scheduled_for`, `expires_at`, and status.
- Celery uses Redis database 2 as broker/result backend. Existing cache and realtime traffic
  remain on databases 0 and 1.
- Celery beat dispatches one reconciliation task every 15 seconds. The task locks due rows
  with `skip_locked`, so retries, multiple workers, and restarts remain idempotent.
- No RabbitMQ, MinIO, Elasticsearch, or database-backed Celery schedule package is added.

## Audience

- `ORG_UNIT` rules carry an explicit `include_descendants` flag. Visibility resolves the
  current portal-backed organization tree, so branch and department subtree rules follow
  organizational changes without copying the directory.
- Position groups use the stable portal contract fields `position_group_external_id` and
  `position_group_name`. Free-form `job_title` is display data and is never an audience key.
- Narrow audience kinds can be combined; `ALL` remains exclusive.

## Media and rich text

- Django `FileSystemStorage` writes random storage keys to the Compose `media-data` volume.
  Original filenames are metadata only.
- Django authorizes `/api/v1/media/{id}/content`; Nginx serves the file only through an
  internal `/_protected_media/` location after receiving `X-Accel-Redirect`.
- Editors may read all media. Employees may read an asset only through at least one currently
  visible published publication. Unauthorized and unknown assets both return 404.
- Upload checks are duplicated at Nginx and Django boundaries. Allowed extensions, detected
  MIME signatures, size, and decoded image validity must agree. HTML, script, executables,
  and SVG are rejected. No scanner service is invented when no corporate scanner exists.
- Rich-text media nodes store `asset_id` only. The frontend converts it to the protected API
  URL at render time; arbitrary image/video URLs and iframe embeds are rejected server-side.

## Pinning, taxonomy, and duplication

- Pin slots are explicit integers 1–5 with unique publication and slot constraints. Regular
  news pagination excludes pinned publications and `/api/v1/news/pinned` returns them in slot
  order.
- Unpublish, expiration, and archive transitions remove a pin in the same transaction.
- Categories and tags are deactivated, not destructively removed from historical content.
- Duplication creates a new draft owned by the actor and copies content, taxonomy, audience,
  and media usages. It never copies lifecycle times, pins, engagement, views, or audit rows.

## Scope boundary

- The immutable Stage 3 release tag is not moved or rewritten. Stage 4 keeps existing
  discussion behavior compatible but does not absorb Stage 5 moderation/statistics or later
  notification, search, and messenger scope.
- Multi-participant approval routes are explicitly deferred; Stage 4 has a single review
  state and editor return/publish/schedule actions.

