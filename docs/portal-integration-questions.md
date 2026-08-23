# Portal integration questions

Status: source-reviewed; portal-specific contract questions remain unanswered
Last reviewed: 2026-08-23

This document is deliberately a question set, not a proposed SSO design. Record each answer with its owner, source (document/API schema/code reference), decision date, and environment applicability. Do not convert assumptions into contract requirements.

## Confirmed by the supplied TZ and UI Kit

The following are requirements or assets already confirmed and should not be re-opened as implementation guesses:

- Employees use existing portal accounts and must not register or maintain a separate module password.
- The portal is authoritative for employee profile, organization, and whether an account is blocked; the module must not become the employee directory master.
- A blocked portal account automatically loses module access, and authorization is enforced server-side on every request.
- Profile data is read-only in the module and organization data supports targeting and employee search.
- The module must use the portal's visual language, be responsive from 360 px, support keyboard use and screen-reader labels, start in Russian, and keep visible strings ready for another language.
- The reviewed UI Kit is `Tandem Portal — UI Kit v2`, covers RU/KK/EN examples, includes light and dark tokens, and embeds Manrope/Inter WOFF2 assets. It does not identify the portal integration transport or its operational owner.

These facts specify required behavior, not the mechanism. The questions below are still required before a real adapter is implemented.

## 1. Ownership and environments

1. Who owns the portal identity, employee directory, organization hierarchy, and role contracts?
2. Who approves integration changes and production access?
3. Which development, test, staging, and production portal environments exist?
4. Are there stable test identities for active, blocked, unknown, and privileged users?
5. What availability, latency, rate-limit, and maintenance-window expectations apply?
6. What versioning and deprecation policy applies to the integration contract?

## 2. Authentication and SSO

1. What is the actual SSO mechanism: portal session cookie, OIDC, OAuth 2.0, SAML, signed reverse-proxy assertion, internal API, or another mechanism?
2. Which component authenticates the original browser request?
3. What exact trusted evidence reaches the module, and how is it cryptographically or operationally validated?
4. If tokens are used, what are issuer, audience, algorithms, key discovery/rotation, claims, clock-skew, expiry, and revocation rules?
5. If cookies are used, what are their names, domain, path, `Secure`, `HttpOnly`, `SameSite`, expiry, renewal, and signing/encryption properties?
6. Can the module validate the portal session directly, or must it call a portal introspection/userinfo endpoint?
7. What is the immutable portal user ID format, length, case sensitivity, and lifecycle?
8. Can a portal user ID ever be reused, merged, or changed?
9. How are service accounts, contractors, duplicate emails, and employees without email represented?
10. What is the login entry flow when the portal session is missing or expired?
11. What is the logout contract: local route, portal route, back-channel logout, session revocation, and post-logout redirect?
12. How quickly must a revoked session or blocked account lose access?
13. Which HTTP status/error code should represent missing, expired, unknown, and blocked identities?
14. Is step-up authentication required for privileged module actions in later stages?

## 3. Embedding and browser topology

1. Will the module be exposed on a subdomain, under a portal path, inside an iframe, or integrated into the portal frontend build?
2. What are the external and internal origins in every environment?
3. Which proxy/CDN/load-balancer components are in the request path?
4. Which proxy addresses are trusted, and which forwarded headers do they overwrite or remove?
5. Is Cloudflare Access only a standalone-environment control, or part of the eventual production path?
6. What CSP, `frame-ancestors`, X-Frame-Options, referrer, and permissions policies apply?
7. What CORS origins, methods, credentials, and headers are allowed?
8. What CSRF mechanism and trusted origins are required?
9. If path-mounted, what base path must the SPA, API, assets, router, and redirects support?
10. Are WebView or legacy browser clients in scope, and what browser support matrix is mandatory?

## 4. Employee profile contract

1. What API, event stream, shared database view, or other source exposes employees?
2. If a shared database is proposed, is read-only access contractually supported, and who owns schema migrations?
3. What are the exact field names, types, nullability, validation rules, and maximum lengths?
4. Which fields are authoritative for full name, email, job title, phone, avatar, organization unit, and active/blocked state?
5. Are names supplied as one display string or structured components, and what locale/script rules apply?
6. Are emails or phone numbers ever hidden by privacy policy?
7. What values distinguish active, blocked, suspended, terminated, on-leave, and deleted employees?
8. Which states may authenticate, and which must be denied?
9. How are profile changes delivered: per-request read, polling, webhook/event, or scheduled synchronization?
10. What freshness requirement applies to each field, especially blocked status?
11. What are pagination, filtering, sorting, and search semantics?
12. Is employee search prefix, substring, token, or full-text; which fields and languages are searchable?
13. What are search result limits, rate limits, and minimum query length?
14. May employee data be cached locally, for how long, and must it be encrypted or deleted on termination?

## 5. Avatar contract

1. Is the avatar represented as an absolute URL, portal-relative URL, file ID, binary endpoint, or data field?
2. Does avatar access require the portal cookie/token or a signed expiring URL?
3. What image formats, dimensions, byte limits, and content types are supported?
4. What is the fallback when no avatar exists?
5. May the module proxy or cache avatars, and what privacy/cache-control policy applies?
6. How are avatar changes and deletions signaled?

## 6. Organization contract

1. What API/event/database source exposes organization units?
2. What is the immutable external organization-unit ID format and lifecycle?
3. What unit kinds exist (company, division, department, team, branch, etc.)?
4. Is the hierarchy a strict tree, a forest, or a graph with multiple parents?
5. Can cycles occur in source data, and how should invalid relationships be handled?
6. How are root units represented?
7. What ordering is authoritative among siblings?
8. How are renames, moves, merges, splits, deactivations, and deletions represented?
9. Can an employee belong to multiple units; which is primary?
10. Are manager/leader relationships part of the contract?
11. Must historical unit references remain resolvable after reorganization?
12. What synchronization/freshness guarantees and expected dataset size apply?

## 7. Roles and authorization

1. Which module roles exist now: employee, author, editor, admin, or others?
2. Are roles owned by the portal, this module, or a combination?
3. Are roles global, organization-scoped, content-scoped, or time-limited?
4. What immutable identifiers should represent roles and scopes?
5. How are role grants, removals, and emergency revocations delivered?
6. May this module persist role projections, and what maximum staleness is acceptable?
7. What is the least-privilege default when role data is missing or the role service is unavailable?
8. Who can audit and change module roles?
9. What authorization decisions must be logged, retained, or exported?

## 8. API and data transport

1. Is the supported integration an HTTP API, RPC, event stream, shared database, or another transport?
2. Where is the authoritative OpenAPI/AsyncAPI/schema documentation?
3. How does the module authenticate to portal services, and how are service credentials issued and rotated?
4. What network path, DNS, TLS/mTLS, firewall, and certificate requirements apply?
5. What are timeouts, retry rules, idempotency guarantees, rate limits, and quotas?
6. What stable error codes distinguish not found, unauthenticated, forbidden, blocked, throttled, unavailable, and invalid data?
7. What pagination model, maximum page size, filtering syntax, and sort stability apply?
8. Are ETags, version numbers, or `updated_at` cursors available for synchronization?
9. Are webhooks/events signed, replay-protected, ordered, and retryable?
10. What backward-compatibility and change-notification commitments exist?

## 9. Failure and consistency behavior

1. If the portal identity service is unavailable, must all authenticated requests fail closed?
2. May a recently validated session be used temporarily during an outage; if so, for exactly how long and for which actions?
3. Must blocked status always be checked live, or is a push/revocation mechanism guaranteed?
4. What should `/health/ready` report when the portal is unavailable but PostgreSQL/Redis are healthy?
5. What user-visible state and support reference should appear for portal outages?
6. How should partial employee/organization responses be handled?
7. How are stale projections detected and repaired?
8. What reconciliation process exists after missed events or a prolonged outage?

## 10. Security, privacy, and audit

1. What employee fields are classified as personal, confidential, or restricted?
2. What retention and deletion policy applies to local projections, logs, traces, and backups?
3. Which fields must never appear in logs or monitoring?
4. Are encryption-at-rest, field-level encryption, data residency, or key-management controls required?
5. What audit events are mandatory for authentication, blocked access, role use, and synchronization?
6. What audit retention, access, export, and tamper-evidence requirements apply?
7. Which security review, threat-model, penetration-test, and vulnerability-scanning gates are mandatory?
8. What incident-response contacts and escalation paths apply?
9. What secret store is approved for portal client credentials and Cloudflare tokens?

## 11. Frontend/UI integration

1. Who owns and versions the supplied `UI Kit v2 (standalone).html`, and what change-notification process applies?
2. The bundle contains local font assets; what licenses and redistribution restrictions apply to extracting them into the application build?
3. Which documented tokens and components are mandatory versus illustrative for Stage 1 review?
4. Beyond the TZ's 360 px minimum, current-browser requirement, keyboard access, and screen-reader labels, what exact browser matrix and WCAG target apply?
5. Is WCAG 2.1 AA, WCAG 2.2 AA, or another standard required?
6. Which Russian terminology is approved for profile, employee directory, access, blocked state, and portal outage?
7. Who supplies and approves Kazakh translations?
8. Must the module inherit portal navigation live, reproduce it, or render only its own content area?
9. The UI Kit defines dark mode and reduced-motion behavior; must Stage 1 expose the theme switch, and are high contrast or right-to-left layouts in scope?

## 12. Operations and rollout

1. Who owns DNS, Cloudflare Tunnel, Cloudflare Access, and production deployment?
2. What hostname and Access allow policy should the standalone environment use?
3. What health/readiness semantics are expected by the deployment platform?
4. What backup, restore, recovery-time, and recovery-point objectives apply?
5. What observability platform, log format, metrics, tracing, alerting, and on-call routing are required?
6. What release, rollback, migration, and maintenance procedures are approved?
7. Is zero-downtime deployment required?
8. What load/concurrency/data-volume targets must Stage 1 demonstrate?
9. What evidence and approvers are required for Stage 1 acceptance?

## Required artifacts from the portal team

- authoritative SSO/session specification;
- example authenticated, unauthenticated, expired, and blocked requests with secrets removed;
- employee and organization schemas plus representative redacted payloads;
- role and authorization matrix;
- API/event/shared-database contract and versioning policy;
- proxy/hostname/cookie/CORS/CSRF topology per environment;
- avatar contract;
- security/privacy/retention requirements;
- operational SLOs, rate limits, and failure semantics;
- named technical and product owners.

Until these are supplied, Stage 1 implements only the typed boundary, development/test mock, and integration documentation. A `RealPortalAdapter` must not be created from guesses.
