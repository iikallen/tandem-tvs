# Tandem Portal Stage 4 acceptance report

Date: 2026-08-23  
Scope: Stage 4 — editorial lifecycle, scheduling, targeting, taxonomy, media and versions  
Result: **PASS locally; release tag is created only after green GitHub CI.** Stage 5 was not started.

## Delivered

- The publication lifecycle is centralized and transactional: `DRAFT`, `IN_REVIEW`,
  `SCHEDULED`, `PUBLISHED`, `UNPUBLISHED`, and terminal `ARCHIVED`, with role checks and
  optimistic `expected_revision` conflicts returned as HTTP 409.
- Immutable canonical snapshots, hashes and changed-field lists are recorded for creation,
  manual saves and lifecycle changes. Autosave runs after 2.5 seconds and coalesces snapshots to
  at most one per actor per minute.
- Celery worker and beat use Redis logical DB 2 and reconcile PostgreSQL every 15 seconds with
  row locking and `skip_locked`. Scheduled publication and expiry are idempotent and restart-safe.
- Exact units, unit subtrees, stable portal position groups, named employees and module roles are
  supported. The same server-side visibility boundary protects feed, detail, discussions and media.
- Pinning uses five unique slots, is separate from the regular feed and is removed automatically
  on unpublish, expiry or archive.
- Editors manage categories, tags and a reusable media library. Uploads use random storage keys,
  a 25 MiB limit, extension/signature/declared-MIME checks, OOXML inspection and decoded image
  validation. HTML, JavaScript, executables and SVG are rejected.
- Media persists in the `media-data` volume and is delivered only after Django authorization via
  `X-Accel-Redirect` to an Nginx `internal` location. Direct and IDOR access remains unavailable.
- The structured editor supports tables, protected images, internal video, attachments and cover
  assets by UUID only. Arbitrary media URLs and iframes are outside the accepted schema.
- Duplication copies editorial content, taxonomy, audience and media references to a new draft,
  without lifecycle times, pins, engagement or source audit history.
- Editorial list/status tabs, review queue, editor/preview, schedule controls, media library,
  taxonomy and version history are responsive and use the UI Kit token system.

## Automated evidence

- Backend: **102 passed** on Python 3.13 / Django 5.2 / pytest 9.1.1.
- Coverage: **92.42% overall** with a 90% gate; publication domain modules are **95–100%** except
  the upload service at 91%, while the aggregate Stage 4 publication domain gate is 95%.
- Ruff format/check, basedpyright (0 errors/warnings), `ty check`, Django check and migration drift
  all pass.
- Frontend: Prettier, ESLint and TypeScript pass; **15 Vitest tests passed**; npm audit reports
  **0 vulnerabilities**.
- Playwright: **19/19 live Chromium tests passed**, including author autosave/reload, review,
  editor publication, addressed/outsider authorization, actual protected media delivery and
  360/390/768/1440 px overflow checks. Previous Stage 1–3 cases remain green.
- Production dependency audit reports **no known vulnerabilities**. Bandit reports zero
  Medium/High findings; its two Low findings are limited to deterministic seed/test settings.

## Real stack and restart evidence

A clean `down -v`, no-cache image build and healthy Compose startup were executed. The first
acceptance attempt exposed and fixed named-volume ownership; the live Nginx test then exposed and
fixed directory traversal permissions while retaining the internal authorization boundary.

`backend/scripts/verify_stage4.py` ran against PostgreSQL, Celery/Redis DB 2 and the mounted media
volume with a backend/worker/beat restart between preparation and verification. Final result:

```text
PASS: restart persistence; scheduled then expired; 4 immutable versions;
duplicate=DRAFT; protected media editor=200, outsider=404, persisted=PASS
```

Stage 2 and Stage 3 PostgreSQL/Redis verifiers remain part of `make prod`. Compose contains
PostgreSQL, Redis, backend, Celery worker, Celery beat, frontend and the optional `tandem-tvs`
Cloudflare tunnel only. Backend, PostgreSQL and Redis have no public host bindings; the local
overlay publishes Nginx on loopback only.

## Cloudflare evidence

- Tunnel: `tandem-tvs`; hostname: `https://tandem-tvs.chatlink.kz`; origin target:
  `http://frontend:80`.
- The rebuilt `cloudflared` service is healthy. Unauthenticated external probes to `/`, live,
  ready, profile, organization and protected-media routes receive Cloudflare Access HTTP 302,
  proving the tunnel and Access boundary are active before origin authentication.
- Authenticated origin/loopback checks return 200 for the application and health endpoints; the
  real Nginx protected-media chain returns 200 to the editor and 404 to an unrelated employee.

## Review and release boundary

Static security review, dependency audits, the complete diff review and executable acceptance
found no unresolved Critical or Major issue. The two material runtime findings (media-volume
write ownership and Nginx read traversal) were fixed and covered by the real-stack acceptance and
Playwright regression.

Stage 4 ends here. Messenger delivery, chats, notifications, moderation and analytics are not
implemented. `main` and tag `stage-4-complete` are updated only after the final Stage 4 CI run is
green.
