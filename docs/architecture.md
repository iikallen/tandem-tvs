# Tandem Portal Stage 1 architecture

Status: discovery baseline verified against the TZ and UI Kit originals
Last reviewed: 2026-08-23

## Requirement authority

The TZ is authoritative for product behavior and acceptance. Its order of precedence is goals, acceptance criteria, functional requirements, then the remaining sections. It deliberately specifies what the module must achieve, while leaving the concrete portal transport, models, and most technical details to implementation.

The UI Kit is authoritative for the portal's visual language. It describes itself as a systematization and extension, not a redesign. The `PortalAdapter`, local projections, endpoint layout, health checks, Redis cache, ASGI server, Nginx, and optional Cloudflare profile below are implementation decisions from the Stage 1 brief; they are not misrepresented as direct TZ requirements.

## Purpose

Stage 1 establishes a standalone, production-shaped module and a narrow integration seam for the existing Tandem corporate portal. It proves deployment, identity projection, access enforcement, employee/organization reads, and the portal UI shell. It does not implement news or messaging features.

## System context

```text
Employee browser
      |
      v
Cloudflare Access (standalone environment policy)
      |
Cloudflare Tunnel (optional Compose profile)
      |
      v
Nginx :80
  |-- / --------------------> React static SPA
  `-- /api/* ---------------> Django ASGI
                                  |-- PortalAdapter
                                  |     `-- MockPortalAdapter (dev/test only)
                                  |-- PostgreSQL (local projections)
                                  `-- Redis (Django cache)
```

Cloudflare may protect the standalone deployment; it is not treated as the future portal SSO contract. The TZ requires valid public HTTPS, while the developer-stand brief selects Cloudflare termination and an optional named tunnel. The real portal authentication mechanism remains unknown until the portal team answers the integration questions.

## Trust boundaries

1. **Internet to Cloudflare.** Public HTTPS terminates at Cloudflare for the standalone environment.
2. **Cloudflare Tunnel to Nginx.** Only the web entry point is reachable. PostgreSQL, Redis, and Django are not published directly.
3. **Nginx to Django.** Proxy metadata is trusted only from the controlled reverse-proxy path and only when production settings explicitly configure it.
4. **Django to PortalAdapter.** All portal-specific authentication and directory behavior crosses the adapter contract.
5. **Adapter to local projections.** Portal data may be cached/projected for module relations and performance, but the portal remains authoritative.

An arbitrary browser-supplied `X-User`, `X-Portal-User`, or similar header is not an authentication mechanism. Mock identity injection is restricted to development/test configuration and must be impossible in production.

## Backend boundaries

### `core`

Owns cross-cutting runtime concerns only:

- liveness and readiness;
- runtime metadata;
- shared exception/API configuration;
- cache/database dependency checks.

### `identity`

Owns:

- the custom passwordless user projection;
- portal authentication for DRF;
- JIT provisioning and per-request profile/status synchronization;
- module-role representation and backend authorization helpers;
- the `portal` integration boundary.

It does not own registration, local credentials, password reset, or an employee directory master.

### `identity.portal`

Defines typed domain values and the minimum adapter contract:

```text
PortalAdapter
  authenticate_request(request) -> PortalIdentity | None
  get_employee(portal_id) -> PortalEmployee | None
  search_employees(query) -> sequence[PortalEmployee]
  list_org_units() -> sequence[PortalOrgUnit]
  healthcheck() -> PortalHealth
```

Exact parameters, failure types, pagination, consistency, and role semantics must be finalized from the real portal contract. Typed dataclasses or similarly strict value objects are preferred over `dict[str, Any]`.

`MockPortalAdapter` is the only Stage 1 implementation. It contains deterministic active employee, author, editor, admin, blocked employee, departments, and a parent-child hierarchy. Adapter contract tests are reusable for a future real implementation.

### `organization`

Owns the local `OrgUnit` projection and organization read API. Stable external IDs allow future module entities to reference organization units without turning PostgreSQL into the directory source of truth.

## Data ownership

| Data | Authority | Local behavior |
| --- | --- | --- |
| Portal identity key | Existing portal | Stored as immutable unique `User.portal_id` |
| Employee profile | Existing portal | Refreshed projection for module use |
| Active/blocked state | Existing portal | Checked on every authenticated request; local projection updated |
| Module password | None | Always unusable; never accepted |
| Organization hierarchy | Existing portal | Local projection keyed by stable external IDs |
| Module roles | Contract to confirm | Read from the trusted adapter and enforced server-side |
| Stage 1 application health | This module | Computed from the application and dependencies |

Deletion, rename, reassignment, and stale-record behavior require a confirmed portal synchronization contract. Until then, the mock demonstrates semantics without implying a real transport.

## Authentication request flow

```text
HTTP request
  -> DRF PortalAuthentication
  -> configured PortalAdapter.authenticate_request
  -> no trusted identity: reject
  -> adapter.get_employee(identity.portal_id)
  -> employee missing: reject
  -> employee blocked/inactive: reject on this request
  -> upsert local User projection by portal_id
  -> set_unusable_password()
  -> synchronize allowed profile fields, org link, roles, and timestamp
  -> request.user
  -> DRF IsAuthenticated + endpoint permission
```

The status check occurs for every new authenticated request. A frontend-only guard is never sufficient. The final choice between HTTP 401 and 403 for blocked users is part of the API error contract and must be consistent across backend, frontend states, and tests.

## Local models

### User projection

Minimum planned fields:

- internal `id`;
- immutable, unique `portal_id`;
- `email`, `full_name`, `job_title`, `phone`, `avatar_url`;
- nullable organization relation;
- `is_active`, `last_portal_sync_at`, `created_at`, `updated_at`.

The model omits `username` unless the reviewed TZ or a framework constraint proves it necessary. A custom manager creates only projected users and always makes the password unusable. `AUTH_USER_MODEL` is configured before the first migration.

### Organization projection

Minimum planned fields:

- internal `id`;
- unique stable `external_id`;
- `name`, `kind`, self-referencing nullable `parent`;
- `is_active`, `created_at`, `updated_at`.

Cycle handling, ordering, root semantics, and deletion policy remain contract questions.

## API surface

All business endpoints are authenticated by default.

| Endpoint | Purpose | Source |
| --- | --- | --- |
| `GET /api/v1/me` | Current read-only projected profile and module roles | Adapter + local projection |
| `GET /api/v1/organization/units` | Organization structure | Controlled projection/adapter |
| `GET /api/v1/organization/employees?search=` | Employee directory search | Adapter or explicitly controlled read model |
| `GET /api/v1/runtime/meta` | Non-secret frontend runtime metadata | Module config |
| `GET /api/v1/health/live` | Process liveness | Module |
| `GET /api/v1/health/ready` | Dependency readiness | Module, DB, cache, adapter as defined |

Profile mutation endpoints are excluded. Health endpoints are anonymous. Runtime metadata is anonymous only if every returned field is safe for public disclosure.

## Frontend architecture

The React application is a static production bundle. React Router owns `/`, `/employees`, and `/profile`; TanStack Query owns server state. A small i18n resource layer supplies every visible string, with Russian initially and Kazakh addable without component changes.

The reviewed UI Kit supplies the exact Stage 1 foundations. The frontend will extract them into project-owned CSS tokens and components rather than copying the standalone documentation page.

### Semantic token baseline

| Role | Light | Dark |
| --- | --- | --- |
| page / surface / subtle / elevated / sidebar | `#F7F8FB` / `#FFFFFF` / `#F1F3F8` / `#FFFFFF` / `#FBFBFD` | `#0F1117` / `#1A1E28` / `#232834` / `#222836` / `#14161F` |
| border default / input / strong / soft | `#ECEEF3` / `#E7E9EF` / `#D5D9E0` / `#F3F4F7` | `#262B36` / `#2C3240` / `#3A4150` / `#20242E` |
| text primary / secondary / muted | `#14171F` / `#4B5566` / `#6B7280` | `#F3F4F7` / `#B7BCC6` / `#9CA3AF` |
| text faint / placeholder / disabled | `#9CA3AF` / `#AEB4C2` / `#B7BCC6` | `#818A9C` / `#7E8797` / `#5A6272` |
| primary / hover / soft | `#3D5AFE` / `#2A54E0` / `#EAF0FE` | `#5B79FE` / `#7C97FE` / `#1C2440` |
| accent / soft | `#F2733A` / `#FDEEE4` | `#F58F5C` / `#3A2416` |
| focus ring / halo | `#3D5AFE` / `#FFFFFF` | `#7C97FE` / `#0F1117` |

The focus treatment is `0 0 0 2px var(--focus-halo), 0 0 0 4px var(--focus-ring)`.

### Elevation baseline

| Token | Light | Dark |
| --- | --- | --- |
| card | `0 1px 2px rgba(20,23,31,0.05)` | `0 1px 2px rgba(0,0,0,0.3)` |
| card hover | `0 10px 24px -12px rgba(20,23,31,0.16)` | `0 10px 24px -12px rgba(0,0,0,0.5)` |
| popover | `0 12px 28px rgba(20,23,31,0.12)` | `0 12px 28px rgba(0,0,0,0.55)` |
| dropdown | `0 16px 32px -10px rgba(15,23,42,0.22)` | `0 16px 32px -10px rgba(0,0,0,0.6)` |
| modal | `0 24px 48px -12px rgba(20,23,31,0.24)` | `0 24px 48px -12px rgba(0,0,0,0.6)` |
| toast | `0 10px 30px -10px rgba(20,23,31,0.25)` | `0 10px 30px -10px rgba(0,0,0,0.6)` |

### Typography, geometry, and motion

- Manrope Variable is the main family. Embedded Inter subsets patch `Ә ә Ғ ғ Қ қ Ң ң Ұ ұ` with `size-adjust: 98.9%`; the WOFF2 assets are available in the bundle for self-hosting.
- Type roles: display `28/800/1.2`; h1 `24/800/1.25`; h2 `20/700/1.3`; h3 `17/700/1.35`; body-lg `15/500/1.5`; body `13/500/1.5`; label `12.5/600/1.4`; caption `11.5/500/1.4`; overline `11/800/1.4`; mono `12/500`.
- Spacing scale: `4, 8, 12, 16, 20, 24, 32, 40, 48, 64` px. Radius scale: `8, 10, 12, 16, 20` px.
- Control heights: `30, 34, 38, 42, 44` px. Icon sizes: `16, 18, 20` px.
- Motion durations: `120, 150, 260` ms. Easing: `cubic-bezier(0,0,.2,1)` and `cubic-bezier(.4,0,.2,1)`. Reduced motion is honored except for essential loading indication.
- Layer order: content 0, sticky 10, sidebar 20, dropdown 30, drawer 40, modal 50, popover 60, toast 70, tooltip 80.

### Stage 1 component mapping

The shell uses the UI Kit's Sidebar, PageHeader/Breadcrumbs/BackLink, FilterBar/Toolbar, Button/IconButton, SearchInput, Avatar/UserChip, Card/DefinitionList/FieldRow, Badge/StatusBadge, DataTable/list states, Skeleton/Spinner, EmptyState, Alert/ApiErrorNote, and permission-gated UI rules. Icon-only controls require an accessible label and tooltip. Permission-sensitive actions are hidden by default and always authorized by the backend.

Both light and dark reference themes rendered correctly during discovery. At 360 px the standalone kit reflowed without an obvious horizontal break; the application itself will still be tested independently at 360, 390, 768, and 1440 px because the reference page is not the product shell.

## Deployment architecture

Production Compose contains:

- Nginx/static frontend image built with `npm ci` and `vite build`;
- Django backend running a production ASGI server;
- PostgreSQL with a named persistent volume;
- Redis used as the Django cache;
- optional `cloudflared` profile using a token from environment/secrets.

Service dependencies use health checks and `condition: service_healthy` where readiness ordering matters. A tunnel deployment targets `http://nginx:80` and need not publish an Nginx host port. Local development may publish explicit ports through a development override.

## Configuration and failure policy

- Settings modules: `base`, `development`, `production`, and `test`.
- Production has `DEBUG=False`.
- `SECRET_KEY`, database credentials, allowed hosts, CSRF trusted origins, Redis URL, and tunnel token come from environment or a secret store.
- Production fails during startup if required settings are absent or if the selected adapter is the mock.
- `SECURE_PROXY_SSL_HEADER` is enabled only for the controlled proxy topology.
- Logs are structured and emitted to stdout without secrets or sensitive portal payloads.
- `.env` files are ignored; `.env.example` contains safe placeholders only.

## Security invariants

- No `/login`, `/register`, password reset, token login, Basic Authentication, or DRF token endpoint.
- No usable local employee passwords.
- No client-controlled identity header in production.
- No access decision enforced only in React.
- No direct publication of backend, PostgreSQL, or Redis.
- No secret in Git, frontend runtime metadata, image layers, logs, or documentation examples.
- No speculative real portal endpoint, cookie, database query, or signing key.
- Production deployment runs Django deploy checks and uses a production ASGI server.

## Quality and evidence

The implementation must leave runnable evidence for adapter behavior, authentication and provisioning, projections, endpoint permissions/contracts, frontend states, accessibility, responsive layouts, production configuration, container readiness, persistence, and restarts. The final acceptance report maps every criterion to implementation, test, command, and observed evidence.

## Architectural decisions deferred to the portal contract

- authentication transport and credential validation;
- identity/session lifetime and logout;
- employee and organization query/sync transport;
- role ownership and authorization mapping;
- stale data, deletion, rename, and reassignment behavior;
- avatar delivery and privacy constraints;
- iframe/path/subdomain embedding and its cookie/CORS/CSRF implications;
- trusted proxy chain and forwarded-header sanitization;
- readiness behavior when the portal is degraded.

These are listed in `portal-integration-questions.md`; none should be answered by inference.
