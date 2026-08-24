# Stage 6 migration plan

## Invariants

- Preserve every `identity.User.id` and all Stage 1–5 foreign keys.
- Never generate a default password.
- Never silently resolve username collisions.
- Final release mode is `LOCAL_ONLY`.

## Schema and data sequence

1. Add nullable `username`, nullable `portal_id`, activation/password timestamps and auth token
   models. Add `AccessGrant` with a unique `(user, module, role)` constraint.
2. Preflight existing data. Abort with a remediation message if normalized portal identifiers
   collide or are blank; do not suffix or rewrite identities silently.
3. Backfill `username` from normalized `portal_id`. Translate legacy roles:
   `employee -> NEWS MEMBER`, `author -> NEWS MEMBER/AUTHOR`,
   `editor -> NEWS MEMBER/EDITOR`, `moderator -> NEWS MEMBER/MODERATOR`, and
   `admin|administrator -> PLATFORM ADMIN/NEWS ADMIN`. Grant active users `MESSENGER MEMBER`.
4. Make `username` non-null and add case-insensitive uniqueness. Keep `module_roles` only as a
   compatibility column; application authorization stops reading it.
5. Existing unusable passwords remain unusable and `activated_at` remains null until invitation.

## Rollout

Deploy A introduces local auth and creates the first administrator with the interactive
`bootstrap_local_admin` command. The command never accepts a password argument. Validate local
login before switching traffic.

Deploy B runs with `AUTH_MODE=LOCAL_ONLY`; `PortalAuthentication` is absent from DRF settings.
Cloudflare Access remains an independent outer perimeter. Rollback restores the preceding image and
schema-compatible migrations; it never rewrites user primary keys.

