# Tandem Portal Stage 2 acceptance report

Date: 2026-08-23  
Scope: Stage 2 — «Публикации и лента»  
Release candidate: `69013b69b870d311e5f5ac9cd7689909c2d44ddb`  
Result: **PASS.** Stage 2 implementation, clean deployment, PostgreSQL acceptance,
Cloudflare Tunnel/Access, independent review, and CI release gates passed. Stage 3 was not
started.

## Delivered vertical slice

- Editors and administrators can create drafts, select `ALL`, exact active organization,
  employee, or module-role audiences, preview safe structured rich text, and publish.
- Employee-facing feed, detail, search, unread state, filters, cursor pagination, and unique
  views all pass through the canonical `Publication.objects.visible_to(user)` boundary.
- Direct detail, search, and unread paths disclose nothing to an employee outside the audience.
- PostgreSQL full-text search weights title `A`, summary `B`, and normalized body `C`; the
  functional GIN index is used by the query plan.
- `/news`, `/news/:id`, and role-protected editorial routes implement the supplied responsive
  UI, including the minimal TipTap toolbar and the shared safe rich-text renderer.

## Automated quality gate

GitHub Actions run `32634738075` completed successfully on the release candidate. Its clean
Ubuntu runner started Compose and executed the repository target literally:

```text
make prod
```

Observed results:

- Ruff format/check: passed for 68 backend files.
- basedpyright: 0 errors, 0 warnings, 0 notes.
- ty: passed.
- Django system/deploy checks: passed.
- Migration drift: no changes detected.
- Backend: 55 tests passed; coverage 87.50%, gate 80%.
- Prettier, ESLint, and TypeScript: passed.
- Frontend: 13 Vitest component/state/accessibility tests passed.
- Playwright: 15 Chromium E2E tests passed, including 360, 390, 768, and 1440 px.
- Vite build: passed; the editor is a separate lazy chunk.
- `npm audit --audit-level=high`: 0 vulnerabilities.
- Docker Compose configuration: passed.

The same checks were run locally after remediation. GNU Make is not installed on the Windows
host, so the literal target is represented by the clean CI run; its component commands were
also run locally.

## Clean deployment and PostgreSQL evidence

After the independent-review fixes, the final local release candidate was exercised with:

```text
docker compose -f compose.yaml -f compose.local.yaml --profile tunnel down --volumes
docker compose -f compose.yaml -f compose.local.yaml --profile tunnel build --no-cache
docker compose -f compose.yaml -f compose.local.yaml --profile tunnel up -d --wait --wait-timeout 240
docker compose exec -T backend uv run --no-sync python manage.py seed_stage2_demo
docker compose exec -T backend uv run --no-sync python scripts/verify_stage2.py
```

The empty volume was recreated, migrations completed, and PostgreSQL, Redis, backend,
frontend, and `cloudflared` became healthy. The deterministic seed created publication
`b7a9e052-b4e6-4f58-8bbf-fc64257261e9`.

The executable PostgreSQL acceptance returned `PASS` and proved:

- all four audience types and union behavior;
- outside-user feed/search exclusion and direct `404`;
- title, summary, and body search;
- unread transitions and one unique view after two detail opens;
- default page size 20 and non-overlapping timeline cursors;
- non-overlapping search cursors after inserting an equal-rank result between pages;
- blocked-user server denial.

`pg_indexes` reports functional GIN index `publications_search_idx`. With sequential scans
disabled for inspection, `EXPLAIN` selected `Bitmap Index Scan on publications_search_idx` for
the weighted search expression. A separate restart check preserved the publication count at
27 before and after restarting PostgreSQL.

## Cloudflare and isolation evidence

- Existing named tunnel: `tandem-tvs`; tunnel ID
  `2c27a4b0-5b7c-4ab8-872e-faece5441ad9`.
- Public hostname: `https://tandem-tvs.chatlink.kz`.
- Tunnel route: `http://frontend:80` with four registered QUIC connections.
- An unauthenticated HTTP client received `302` from `/` and every checked API route, proving
  Cloudflare Access intercepted the request without returning application data.
- An authenticated allowed browser session received `200` from `/`, live/ready health,
  `/api/v1/me`, and `/api/v1/organization/units`; readiness reported database, cache, and
  portal components `ok`.
- Through the external hostname, the addressed engineering employee found and opened the
  organization publication. After switching the deterministic portal projection to an
  outside employee, search omitted its UUID and the direct URL returned `404`.
- Compose publishes only Nginx at `127.0.0.1:8080`. Backend, PostgreSQL, and Redis expose no
  host ports; the Cloudflare route targets only frontend.
- Backend runs as UID/GID 10001 and frontend as UID/GID 101. Both root filesystems rejected
  write probes.
- The tunnel token was copied from the authenticated Cloudflare dashboard into the Compose
  process environment. It was not printed, committed, or written to a project file.

This external proof intentionally uses the deterministic development `PortalAdapter`.
Production settings continue to reject that mock and fail closed until the authoritative
portal integration contract is supplied.

## Independent review

The first independent Stage 2 review found 0 Critical and 3 Major issues:

1. an employee audience target did not verify that the adapter returned the requested portal
   identity;
2. search pagination used a non-unique rank as its cursor position;
3. QuerySet bulk operations bypassed instance-level append-only audit guards.

All three were fixed with regression coverage. Search now uses a fixed-width
`rank:full-UUID` position, preserving weighted relevance while making the first cursor field
unique. PostgreSQL insertion acceptance verifies stability. The reviewer rechecked the
remediation and reported **0 Critical and 0 Major remaining**, with no new release blocker.

## Release boundary

The Stage 2 branch contains publications, feed, editorial UI, search, unread, and views only.
Comments, reactions, messenger/WebSockets, notification delivery, moderation, analytics, and
other Stage 3/4 domains were not implemented. The release procedure merges this exact history
to `main` and tags it `stage-2-complete` only after the report commit itself receives green CI.
