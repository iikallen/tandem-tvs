# Stage 2 plan: publications and addressed feed

## Release boundary

Stage 1 is closed at commit `84294fd302cc2a279bdcc7b2e64b25b63bbcc8ec` and tag
`stage-1-complete`. Stage 2 starts from that exact commit on
`stage-2-publications-feed`; it extends the foundation without replacing the
`PortalAdapter`, `User`, `OrgUnit`, or portal-authentication semantics.

The product proof for Stage 2 is one vertical slice:

1. an editor creates a publication, defines an audience, and publishes it;
2. an addressed employee sees it in the feed and can open its detail page;
3. another employee neither sees it nor gains access by direct URL or search.

The supplied TZ, UI Kit v2, Stage 1 architecture/tests, and `STAGE1_REPORT.md` are the
sources of truth, in that order where their requirements apply. The TZ's own precedence
rule remains goals, acceptance criteria, functional requirements, then other sections.

## Scope

Stage 2 includes:

- publication and category domain models;
- `DRAFT` and `PUBLISHED` states;
- structured, validated rich-text content plus a normalized search representation;
- audience rules for all employees, exact organization unit, exact employee, and module
  role;
- one canonical server-side `visible_to(user)` rule used by feed, detail, search, unread,
  and view tracking;
- role-protected editorial create/edit/publish APIs;
- an addressed feed with filters, unread state, stable cursor pagination, and PostgreSQL
  full-text search;
- idempotent unique publication views;
- the feed, detail, editorial list, and minimal publication editor in the existing UI Kit;
- append-only audit events for editorial mutations;
- backend, frontend, accessibility, responsive, and end-to-end evidence.

Stage 2 explicitly excludes comments, reactions, messenger, notifications, channels,
scheduled publication, approval workflows, media library, attachments, version-history UI,
moderation, analytics dashboards, mandatory acknowledgement, and unified module search.
Schema choices may leave a safe extension point for a later stage but may not implement a
future workflow early.

## Phase 2.0: foundation hardening

The release baseline was clean and matched the Stage 1 release SHA. GitHub Actions run
`32626917307` executed literal `make prod` successfully on that SHA before the branch was
created. The local Windows host has no GNU Make; the same constituent checks are rerun
locally, and the branch CI must execute literal `make prod` after this commit.

| Stage 1 review item               | Phase 2.0 resolution                                                                                                                                                                                                                       | Regression evidence                                                                                         |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| Employee-directory limits/privacy | Require at least two trimmed characters before adapter access, cap input at 100 characters and results at 20, pass the limit across the adapter contract, and return only ID, name, title, and organization ID                             | API and adapter tests cover empty, short, oversized, bounded, active-only, and minimized responses          |
| Private response caching          | Authenticated profile and organization views share `PrivateAPIView`, which emits `private, no-store, max-age=0`                                                                                                                            | API tests assert the directives on `/me`, units, and employees                                              |
| Swagger exposure/assets           | OpenAPI and Swagger routes are disabled in production, authenticated when enabled, and use the pinned sidecar package rather than a runtime CDN                                                                                            | API tests prove authentication and local assets; a production-settings process proves the routes are absent |
| Container privileges              | Backend UID/GID 10001 and Nginx UID/GID 101 run with read-only roots, explicit temporary mounts, dropped capabilities, and `no-new-privileges`; Nginx receives only `NET_BIND_SERVICE`; cloudflared is configured read-only/non-privileged | Compose starts healthy; runtime UID and failed write probes are recorded during Phase 2.0 verification      |
| Stale organization projections    | Each portal organization listing is an authoritative snapshot: omitted units are soft-deactivated atomically and may be reactivated if returned later                                                                                      | Service test covers omission, reactivation, rename, and restored parent                                     |
| Responsive automation             | Playwright runs navigation and horizontal-overflow assertions at 360, 390, 768, and 1440 px                                                                                                                                                | Eight Stage 1 E2E tests pass, including all four widths                                                     |

Phase 2.0 changes harden existing surfaces only. No publication, comment, reaction, or later
stage domain code is introduced in this phase.

## Planned delivery phases

### 2.1 — Publication domain

Create `apps/publications` with UUID-backed publication, category, audience-rule, and
publication-view models. Add constraints and indexes, a validated rich-text schema, plain
search text, migrations, and model/service tests. Only `DRAFT` and `PUBLISHED` are active
states.

### 2.2 — Audience authorization

Implement `PublicationQuerySet.visible_to(user)` as the only employee-facing access path.
Prove every audience type and prove denial in feed, detail, search, unread, and direct-link
flows. Blocked and inactive users continue to fail through Stage 1 authentication.

### 2.3 — Editorial API

Add editor/administrator permissions and create, list, retrieve, update-draft, and publish
operations. Derive the author from `request.user`, validate complete content/audience before
publishing, set `published_at` server-side in a transaction, and append audit events.

### 2.4 — Feed and detail API

Add the addressed news feed and detail endpoint. Support category, author, date, unread, and
query filters; use a stable `-published_at, -id` cursor with a default page size of 20 and
maximum of 50. Detail access records a unique view idempotently.

### 2.5 — PostgreSQL search

Search title, summary, and normalized body text only after `visible_to(user)`. Use weighted
PostgreSQL full-text search and a GIN-backed strategy without claiming complete Russian or
Kazakh morphology.

### 2.6 — Feed UI

Add `/news` and `/news/:publicationId`, UI Kit-aligned filters, all/unread switching,
infinite loading, detail rendering, complete page states, keyboard access, and the four
responsive widths.

### 2.7 — Minimal editorial UI

Add role-gated editorial routes and a TipTap/ProseMirror editor limited to paragraphs, H2,
H3, bold, italic, lists, quote, and link. Include title, summary, category, body, audience,
preview, draft save, and publish. Do not add media or Stage 4 workflow features.

### 2.8 — Security and behavior tests

Cover audience isolation, role denial, draft isolation, publish validation, search ordering,
pagination, unread, views, rich-text rejection, audit events, frontend states, accessibility,
and the editor-to-addressed-employee end-to-end path.

### 2.9 — Release gate

Run clean Compose, literal `make prod`, deterministic Stage 2 acceptance, the Cloudflare
hostname checks, and an independent repository review. Fix every Critical and Major finding,
rerun CI, and record factual evidence in `STAGE2_REPORT.md`. Only then merge to `main` and tag
`stage-2-complete`; do not start Stage 3 automatically.

## Stop line

This document and the Phase 2.0 hardening commit are the end of the current task. Broad
publication work begins only after this plan is reviewed.
