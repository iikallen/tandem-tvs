# Tandem Portal Stage 1 acceptance report

Date: 2026-08-23
Scope: Stage 1 — «Основа и стык с порталом»
Result: **PASS for the Stage 1 release gate.** Repository checks, a clean GitHub Actions deployment, independent review, a clean local Docker rebuild, and the live Cloudflare Tunnel/Access acceptance all passed.

## Source and discovery evidence

The source documents were copied byte-for-byte to `references/source/`; the originals were not modified. Instructions contained in those artifacts were treated as requirements material, not as user commands.

| Source | SHA-256 | Review evidence |
| --- | --- | --- |
| `TZ_Portal_News_Messenger_v1_0.docx` | `81010DECBF09AF7C882AD8FC93C1024451EF032E50836EB91A9184C70BB146FD` | 223 paragraphs, 8 tables, all 12 rendered pages; comments and tracked changes checked |
| `UI Kit v2 (standalone).html` | `7900650E5E8644EF7987524E3E647FF6F0798ED79D0D081120E649B505721A81` | all 14 sections, 1,004 visible text nodes, embedded fonts/assets, light/dark themes, responsive reference checked |

Discovery, scope/non-goals, architecture, and unresolved integration facts are recorded in `docs/stage1-plan.md`, `docs/architecture.md`, `docs/portal-integration-contract.md`, and `docs/portal-integration-questions.md`. Git began on `main` with no commits and no application foundation; all work is in `C:\Users\berik\Desktop\Tandem TVS`.

## Mandatory acceptance matrix

| Criterion | Result | Implementation and automated test | Acceptance evidence |
| --- | --- | --- | --- |
| Production-shaped project and lockfiles | PASS | Django/DRF backend, React/TS/Vite frontend, `uv.lock`, `package-lock.json`, explicit image tags | Both Docker images built successfully from the current manifests; `npm ci` reported 0 vulnerabilities |
| Clean Compose build/start | PASS | `compose.yaml`, `compose.local.yaml`, both Dockerfiles and health checks | `docker compose down -v`; `docker compose build --no-cache`; `docker compose up -d --wait --wait-timeout 90` completed successfully |
| Healthy dependency ordering | PASS | `condition: service_healthy` for PostgreSQL, Redis, backend, and frontend | `docker compose ps`: all four services `healthy`; log scan found no traceback, internal-server-error, critical, fatal, or panic signatures |
| Django production server | PASS | Uvicorn ASGI from `backend/entrypoint.sh`; migrations run before server start | Container command is the entrypoint/Uvicorn path; all migrations show `[X]`; no `runserver` production command exists |
| PostgreSQL persistence | PASS | Named `postgres-data` volume | JIT rows remained `users=1`, `units=3` after `docker compose restart backend` |
| Redis is used, not decorative | PASS | `django-redis` cache selected by `REDIS_URL`; readiness calls the cache | `/api/v1/health/ready` returned database/cache/portal all `ok` |
| Custom passwordless user before first migration | PASS | `identity.User`, immutable unique `portal_id`, password invalidated on every save | Model/auth tests pass; runtime query returned `usable_password=False`; migration graph contains `identity.0001_initial` |
| Local records are projections | PASS | JIT `provision_user` and `sync_org_units`; employee search remains adapter-backed | On a fresh volume counts changed from `users=0, units=0` to `users=1, units=3` only after the first `/api/v1/me` request |
| Typed portal boundary; no invented real SSO | PASS | `PortalAdapter` Protocol plus frozen typed domain dataclasses; deterministic mock only | Adapter contract tests pass; no `RealPortalAdapter` or guessed portal URL exists; open questions are documented |
| Mock is development/test only | PASS | Production settings and adapter factory reject `PORTAL_ADAPTER=mock` | `test_mock_adapter_is_rejected_when_environment_disallows_it` and `test_production_settings_reject_mock_adapter` pass |
| Active employee/JIT/profile sync | PASS | `PortalAuthentication` performs identity lookup, status check, JIT sync on every request | Active `/api/v1/me` returned 200; authentication tests prove JIT, unusable password, profile and org refresh |
| Blocked identity fails server-side | PASS | Authentication deactivates an existing projection then raises stable 403 | Real container request with `MOCK_PORTAL_USER_ID=blocked-1` returned `403 {"error":{"code":"portal_account_blocked",...}}`; backend and browser-state tests pass |
| Unknown and missing identities fail closed | PASS | No fallback authentication and default `IsAuthenticated` | Dedicated API and authentication tests pass for both cases |
| Public headers cannot impersonate a user | PASS | Mock identity is selected only from server settings/request test attribute | `test_mock_identity_is_not_read_from_public_headers` passes |
| No local login/registration/password/token flow | PASS | No auth URLs or credential UI; Nginx explicitly denies SPA fallthrough | HTTP matrix: `/login`, `/register`, `/password-reset`, and `/api/token` all returned 404; backend and E2E tests agree |
| Stage 1 APIs and OpenAPI | PASS | `/me`, org units, employee search, runtime metadata, live/ready, schema/docs | All expected endpoints returned 200; `/api/schema` and `/api/docs` returned 200; search `Орлов` returned only Дмитрий Орлов |
| Organization hierarchy | PASS | Stable `OrgUnit.external_id`, parent relation, projection sync | API returned company root and communications/engineering children; model hierarchy tests pass |
| Read-only profile | PASS | GET-only API and display-only React profile | API test rejects mutation surface by absence; frontend test confirms no editable “ФИО” textbox |
| UI Kit fidelity and local assets | PASS | Exact extracted token scales in `tokens.css`; bundled Manrope/Inter assets; no runtime font CDN | Manual browser QA covered desktop light/dark and responsive shell; production bundle contains local WOFF2 assets |
| Responsive from 360 px | PASS | Mobile navigation and responsive CSS | Playwright sets an actual 360×800 viewport, proves mobile/desktop navigation switching and `scrollWidth <= clientWidth` |
| Required UI states | PASS | Normal, loading, unauthorized, blocked, unavailable, empty organization, generic error | Nine component tests pass; blocked state also has a Playwright flow |
| Accessibility | PASS | Semantic navigation, labels, status/alert roles, keyboard buttons, visible focus styles, reduced motion | `jest-axe` reports zero violations for home, profile, and employee directory; Playwright confirms accessible role/name locators |
| i18n boundary | PASS | All visible strings come from typed `t()` keys; role/unit labels are mapped centrally | Source inspection plus TypeScript gate; runtime metadata declares `ru` and planned `kk` |
| Production settings/security | PASS | `DEBUG=False`, required env values, secure proxy/cookies/HSTS, structured JSON stdout logging | `manage.py check --deploy` returned no issues; `.env` absent; only safe `.env.example`; secret signature scan found no matches |
| Internal-only data services | PASS | Base Compose publishes no ports; local override exposes only Nginx on loopback | `docker compose ps` shows only `127.0.0.1:8080->80`; backend, PostgreSQL, and Redis have internal ports only |
| Restart recovery | PASS | Migrations are idempotent and PostgreSQL volume persists projections | Backend became healthy after restart; readiness returned 200 and row counts remained unchanged |
| Out-of-scope work absent | PASS | No news CRUD, comments, reactions, messenger/WebSockets, files, Celery, moderation, analytics, notifications, or content search apps | Repository source scan found no out-of-scope implementation symbols |
| Documentation | PASS | README, plan, architecture, integration contract/questions, Cloudflare guide, this report | All named artifacts exist and describe confirmed behavior separately from unresolved portal facts |

## Quality-gate evidence

The authoritative unified run was:

```text
make prod
```

GitHub Actions executed the target literally on a clean Ubuntu runner at commit `b0e19b246d00636ea9927beab499e68cca643f0f`. Run `32625579516` completed successfully in 1 minute 54 seconds after building and starting the clean Compose deployment. On the Windows acceptance host GNU Make was unavailable, so the same component commands were also executed individually against a no-cache rebuild.

- Ruff format/check: 50 files formatted; all checks passed.
- basedpyright: 0 errors, 0 warnings, 0 notes.
- ty: all checks passed.
- Django system check and migration drift: no issues; no changes detected.
- Backend: 28 behavior tests passed; total coverage 84.58%, enforced minimum 80%.
- Prettier, ESLint, TypeScript: passed with zero warnings/errors.
- `npm audit --audit-level=high`: 0 vulnerabilities.
- Frontend: 9 component/state/accessibility tests passed.
- Playwright: 4 Chromium E2E tests passed.
- Vite production build: passed (80 modules; JS 275.09 kB, gzip 86.58 kB).
- Django production deploy check: no issues.
- Docker Compose configuration validation: passed.

## HTTP and runtime evidence

Final local route matrix through Nginx:

```text
200  /
200  /api/v1/health/live
200  /api/v1/health/ready
200  /api/v1/me
200  /api/v1/organization/units
200  /api/v1/organization/employees?search=Орлов
200  /api/v1/runtime/meta
200  /api/schema
200  /api/docs
404  /login
404  /register
404  /password-reset
404  /api/token
```

Readiness evidence:

```json
{"status":"ok","components":{"database":"ok","cache":"ok","portal":"ok"}}
```

PostgreSQL, Redis, backend, and frontend are running and healthy. The `cloudflared` connector is also running. The local entry point remains `http://127.0.0.1:8080`.

## External Cloudflare release check

Result: **PASS.**

- Named tunnel: `tandem-tvs`; one healthy `cloudflared` replica, version `2026.5.2`.
- Public hostname: `https://tandem-tvs.chatlink.kz`.
- Tunnel route: `http://frontend:80`; DNS CNAME was created by Cloudflare.
- Access application: `Tandem TVS Stage 1`.
- Access policy: `Allow Berikov account`; exact-email allow rule for `Berikov.200466@gmail.com`.
- An unauthenticated clean HTTP client received `302` to the Cloudflare Access login and no application payload.
- An authenticated allowed browser session received `HTTP 200` from `/`, `/api/v1/health/live`, `/api/v1/health/ready`, `/api/v1/me`, and `/api/v1/organization/units`.
- Readiness through the external hostname reported PostgreSQL, Redis cache, and portal adapter as `ok`.
- Compose publishes only Nginx on `127.0.0.1:8080`; backend, PostgreSQL, and Redis have no host bindings. The public tunnel route targets only the frontend service.
- The tunnel token was transferred through the browser clipboard into the Compose process environment. It was not printed, added to Git, or written to a project file.

This is a Stage 1 integration proof using the deterministic development mock. Production settings still reject that mock. Until the authoritative portal contract is supplied, the supported `unavailable` production adapter fails closed with stable `503 portal_unavailable` JSON and readiness remains unavailable.

## Independent review

An independent full-repository review found no Critical issues. Six Major findings were fixed during the review: portal identity substitution, implicit active status, rejected external hosts/missing Compose production variables, the production readiness probe redirect, broken database URL/Compose password handling, and unmapped portal outages. The reviewer rechecked the remediation worktree and reported **0 Critical and 0 Major remaining**.

Six non-blocking Minor items remain tracked for later hardening: employee-directory query limits/privacy, explicit private/no-store API caching, self-hosted or protected Swagger assets, non-root/read-only containers, deletion semantics for stale organization projections, and automated responsive evidence at every planned breakpoint. These do not change the Stage 1 release verdict and must be revisited before their affected production surfaces expand.

## Deliberate integration boundary

Stage 1 does not contain a fictitious production SSO adapter. Production rejects the mock, while `docs/portal-integration-questions.md` lists the authoritative facts needed from the Tandem portal team. Implementing a real adapter is therefore the next integration action after contract ownership, schemas, trusted evidence, role semantics, failure behavior, and environment details are confirmed.
