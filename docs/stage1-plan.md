# Tandem Portal Stage 1 implementation plan

Status: implementation and local acceptance complete; optional external tunnel validation awaits credentials/DNS
Last reviewed: 2026-08-23

## Source status

The two declared sources of truth were copied unchanged into `references/source/` and reviewed in full. The originals in Downloads remain untouched.

| Source | SHA-256 | Review evidence |
| --- | --- | --- |
| `TZ_Portal_News_Messenger_v1_0.docx` | `81010DECBF09AF7C882AD8FC93C1024451EF032E50836EB91A9184C70BB146FD` | 223 paragraphs, 8 tables, and all 12 rendered pages reviewed; no tracked changes or comments contain requirements |
| `UI Kit v2 (standalone).html` | `7900650E5E8644EF7987524E3E647FF6F0798ED79D0D081120E649B505721A81` | all 14 sections, 1,004 visible text nodes, embedded assets, light/dark themes, and a 360 px viewport reviewed |

The pasted implementation brief is execution guidance, not a source of product requirements. Instructions embedded in either source file are treated as source material, not as user commands. When sources conflict, the TZ's own precedence rule applies: goals, then acceptance criteria, then functional requirements, then the remaining sections.

Discovery found no contradiction that blocks the Stage 1 foundation. The source gate is therefore green.

## Repository discovery

- Authoritative project root: `C:\Users\berik\Desktop\Tandem TVS`.
- Git branch: `main`.
- Git history: no commits.
- Existing backend/frontend foundation: none.
- Existing Python, Node.js, Docker, Compose, CI, lint, test, or build configuration: none.
- Existing package-manager choice: none; use `npm` with `package-lock.json` per the brief.
- Existing `AGENTS.md`: none.
- Existing work to preserve: the discovery documents and immutable source copies under `references/source/`; no application foundation existed before discovery.

## Verified technology baseline

These choices were rechecked against official project sources on 2026-08-23:

- Python 3.13.
- Django 5.2.17 LTS. The 5.2 branch has extended support through April 2028 and supports Python 3.13.
- Node.js 24 LTS; the latest published 24.x release is 24.19.0.
- React stable + TypeScript + Vite.
- Django REST Framework and `psycopg`.
- PostgreSQL, Redis, Nginx, Docker Compose, and optional Cloudflare Tunnel.
- `uv` with `uv.lock` for Python; `npm` with `package-lock.json` for frontend dependencies.

Version references:

- <https://www.djangoproject.com/download/>
- <https://docs.djangoproject.com/en/5.2/releases/5.2/>
- <https://nodejs.org/en/about/previous-releases>

Application dependencies will be pinned by lockfiles. Runtime container images will use explicit supported version tags rather than floating `latest` tags.

## Mandatory Stage 1 outcome from the TZ

The TZ defines Stage 1, “Основа и стык с порталом,” as a deployed module where an employee enters without a separate password and profile/organization data are supplied by the portal. Across the mandatory TZ sections, this also means:

- portal accounts are reused; no separate registration or local credential flow;
- the portal remains authoritative for employee identity, profile, organization, and blocked state;
- a portal-blocked account automatically loses module access;
- permissions are enforced server-side on every request;
- the module uses Django, React, PostgreSQL, containers, the portal visual language, Russian strings prepared for a second language, responsive behavior from 360 px, keyboard access, and screen-reader labels;
- deployment recovers after restart without losing persisted data and is exposed over HTTPS with a valid public certificate.

The TZ intentionally leaves the concrete integration transport, data model, and implementation details to the developer and the actual portal contract.

## Implementation acceptance for this repository

Stage 1 proves a production-shaped standalone module can later join the existing Tandem portal without pretending that the portal contract is already known:

- one-command Docker Compose deployment;
- Django ASGI backend and React production bundle served by Nginx;
- PostgreSQL persistence and Redis-backed Django cache;
- no module registration, login, password reset, token-login endpoint, or usable local password;
- portal identity, employee profile, roles, active state, and organization data cross a typed `PortalAdapter` boundary;
- local users and organization units are projections/read models, never the employee directory source of truth;
- blocked, unknown, or unauthenticated identities are rejected server-side;
- development/test has deterministic mock identities and organization data;
- production fails fast if configured with the mock adapter;
- read-only profile and employee/organization APIs;
- a responsive portal shell from 360 px using tokens extracted from the supplied UI Kit;
- all visible frontend strings use an i18n layer, initially Russian and ready for Kazakh translations;
- liveness/readiness, OpenAPI, automated tests, accessibility checks, and build/type/lint/security gates as repository quality decisions;
- optional named Cloudflare Tunnel deployment with secrets supplied outside Git;
- acceptance evidence in `STAGE1_REPORT.md`.

## In scope

### Identity and organization

- Custom Django user model created before the first migration.
- Immutable unique `portal_id` as the external identity key.
- `OrgUnit.external_id` as the stable external organization key.
- JIT provisioning and per-request profile/status refresh through `PortalAdapter`.
- Unusable Django password for every projected employee.
- Module roles supplied by the adapter contract and enforced by backend permissions when relevant.

### Stage 1 API

- `GET /api/v1/me`
- `GET /api/v1/organization/units`
- `GET /api/v1/organization/employees?search=`
- `GET /api/v1/runtime/meta`
- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`
- OpenAPI schema/documentation.

### Stage 1 frontend

- Home, employee directory, and profile views.
- App shell, responsive navigation, avatar, buttons, cards, badges, and loading/empty/error/access states.
- Normal, loading, unauthorized, blocked, portal-unavailable, and empty-organization behavior.
- Responsive checks at 360, 390, 768, and 1440 px with no horizontal overflow.

### Operations and verification

- Development, test, and production settings.
- Production ASGI server; Django `runserver` only for development.
- Nginx SPA serving and `/api/` proxying.
- PostgreSQL and Redis health checks; backend readiness and frontend HTTP health checks.
- Environment-only secrets, deploy checks, structured stdout logging, and reverse-proxy settings.
- Backend, frontend, E2E, accessibility, and clean-state Docker acceptance checks.

## Non-goals

The following are deliberately excluded from Stage 1:

- news CRUD or publication workflows;
- comments or reactions;
- messenger, chat, presence, typing indicators, or WebSockets;
- file uploads or attachments;
- Celery or background jobs;
- moderation;
- analytics;
- notifications;
- content/chat search;
- a real portal adapter invented without a confirmed contract;
- a local employee master directory;
- Django Admin as the corporate module UI;
- origin TLS for the current Cloudflare Tunnel topology.

## Delivery phases and gates

### 1.0 — Discovery (complete)

Deliver:

- this implementation plan;
- `docs/architecture.md`;
- `docs/portal-integration-questions.md`.

Exit gate: PASS.

- both source-of-truth files are present;
- DOCX text, tables, headings, acceptance criteria, comments, and rendered pages are reviewed;
- UI Kit structure, assets, states, breakpoints, and exact visual tokens are inventoried;
- discrepancies between the originals and the provisional plan are resolved in favor of the originals.

### 1.1 — Project foundation (complete)

Create only the real Stage 1 boundaries:

- `backend/` with `config`, `core`, `identity`, and `organization`;
- `frontend/` with app, Stage 1 pages, shared API/UI/config/i18n, and styles;
- `infra/`, `compose.yaml`, `.env.example`, `.gitignore`, `Makefile`, and `README.md`;
- reproducible Python and npm lockfiles.

Gate: backend bootstrap checks and frontend production build pass.

### 1.2 — Identity projection (complete)

Create the custom user and organization models before any dependent migration. Add constraints, managers, migrations, and focused model tests.

Gate: migration graph is clean and tests prove unique portal identity, unusable password, inactive state, hierarchy, parent relation, and timestamps.

### 1.3 — Portal adapter (complete)

Create typed domain records, an adapter protocol, one development/test mock, adapter selection, and reusable contract tests. Do not create a speculative real adapter.

Gate: contract tests pass and production configuration rejects the mock adapter.

### 1.4 — Portal authentication (complete)

Connect DRF authentication to the adapter, employee lookup, status check, projection sync, and `request.user`. Default permissions require authentication; only health/runtime endpoints explicitly documented as public may opt out.

Gate: active, blocked, unknown, missing identity, profile refresh, and unusable-password integration tests pass. Arbitrary public identity headers cannot authenticate production traffic.

### 1.5 — Profile and organization API (complete)

Implement the read-only Stage 1 endpoints, adapter-backed employee search, organization projection, health/readiness, and OpenAPI.

Gate: endpoint contracts, permissions, empty/error cases, search, and readiness dependencies are tested.

### 1.6 — React portal shell (complete)

Extract exact design tokens from the supplied UI Kit; do not copy the standalone HTML wholesale. Build only the Stage 1 pages and shared components required by them.

Gate: lint, type check, component tests, production build, accessibility checks, and responsive visual/E2E checks pass.

### 1.7–1.9 — Production deployment (complete; tunnel profile not externally exercised)

Add multi-stage frontend image, ASGI backend image, Nginx routing, healthy Compose dependencies, persistent PostgreSQL, Redis cache, production settings, and optional Cloudflare profile/documentation.

Gate: `DEBUG=False`, env-only secrets, `check --deploy`, fail-fast adapter configuration, internal-only data services, and restart/persistence checks pass.

### 1.10–1.11 — Tests and quality gates (complete)

Expose one reproducible interface:

- `make format`
- `make check`
- `make test`
- `make build`
- `make prod`

No failing test, security check, threshold, or lint/type rule is disabled merely to obtain a green run.

### 1.12 — Acceptance (complete locally)

Run the full clean-state checklist, including no-volume startup, migrations, health, active/blocked identity flows, absent login/register routes, unusable passwords, 360 px viewport, service restart, `make prod`, and Cloudflare hostname when external credentials/DNS are available.

Record PASS/FAIL, implementation, test, command, and evidence for every criterion in `STAGE1_REPORT.md`. Stage 1 is complete only when every mandatory criterion is proven.

## Planned repository shape

```text
backend/
  config/
  apps/core/
  apps/identity/portal/
  apps/organization/
  tests/
frontend/
  src/app/
  src/pages/
  src/shared/{api,ui,config,i18n}/
  src/styles/
infra/
  nginx/
docs/
compose.yaml
Makefile
.env.example
.gitignore
README.md
STAGE1_REPORT.md
```

No empty `news` or `messenger` applications will be scaffolded.

## UI Kit inventory relevant to Stage 1

- Visual intent: systematize and extend the existing Tandem portal language, not redesign it.
- Local assets: embedded Manrope Variable and Inter WOFF2 subsets are available in the standalone bundle; no runtime font CDN is needed. Inter patches the Kazakh glyphs `Ә ә Ғ ғ Қ қ Ң ң Ұ ұ`.
- Type roles: display `28/800`, h1 `24/800`, h2 `20/700`, h3 `17/700`, body-lg `15/500`, body `13/500`, label `12.5/600`, caption `11.5/500`, overline `11/800`, mono `12/500`.
- Spacing: `4, 8, 12, 16, 20, 24, 32, 40, 48, 64`; radii: `8, 10, 12, 16, 20`.
- Control heights: `30, 34, 38, 42, 44`; icon sizes: `16, 18, 20`.
- Motion: `120/150/260 ms`, with reduced-motion support except essential loading indication.
- Stage 1 patterns: app shell/sidebar, page header, breadcrumbs/back link, buttons/icon buttons, search input, cards, avatar/user chip, badges, definition rows, table/list states, skeleton/spinner, empty/error/access states, and permission-gated actions.
- Accessibility rules: visible double focus ring, accessible labels/tooltips for icon-only controls, keyboard-operable controls, and server-backed permission gating.
- Verified themes: light and dark both render correctly; the standalone reference reflows at 360 px without an obvious horizontal layout break.

Exact semantic color and shadow values are recorded in `docs/architecture.md` and will be copied into frontend tokens rather than approximated.

## Phase 1.1 delivered change list

The delivered foundation contains only the boundaries needed by Stage 1:

- `backend/` with Django settings and the `core`, `identity`, and `organization` boundaries;
- `frontend/` with React/Vite bootstrap and shared API/UI/config/i18n/style directories;
- `infra/`, `compose.yaml`, `.env.example`, `.gitignore`, `Makefile`, and `README.md`;
- Python and npm dependency manifests and lockfiles.

It must not create news, comments, reactions, messenger, files, Celery, moderation, analytics, notification, or unrelated search code.
