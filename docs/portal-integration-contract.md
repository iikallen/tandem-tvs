# Portal integration contract boundary

Status: transport pending confirmation from the Tandem portal team.

The application depends only on the typed `PortalAdapter` boundary. A future real adapter must authenticate trusted portal evidence, fetch one employee, search employees, list organization units, and report dependency health. It must return the existing typed domain records and stable failure semantics; application services and views must not depend on its transport.

## Required behavior

- `authenticate_request` validates trusted evidence and returns an immutable portal identity or no identity.
- `get_employee` returns the authoritative profile, roles, organization key, and active/blocked state.
- `search_employees` follows the agreed search, privacy, pagination, and rate-limit contract.
- `list_org_units` returns stable external IDs and parent IDs without making the module the organization master.
- `healthcheck` exposes only availability needed by readiness, never secrets or employee payloads.

Every authenticated request checks the portal-backed employee state. Unknown and missing identities fail closed; blocked employees receive a stable backend denial. Local `User` and `OrgUnit` rows are projections only and cannot provide a fallback local login.

`MockPortalAdapter` is deterministic development/test data. Production settings reject it at import time. No `RealPortalAdapter` will be implemented until the unanswered items in `portal-integration-questions.md` have authoritative owners and examples.
