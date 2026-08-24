# Stage 6 requirement amendment

## Approved change

Tandem owns authentication, credentials, account status, sessions and authorization for both
News and the future Messenger module. Portal SSO is no longer required to sign in. This decision
supersedes the original portal-only authentication requirement.

The existing `identity.User` remains the single account and retains its primary key so all Stage
1–5 foreign keys and history remain valid. Separate News and Messenger user tables are forbidden.

## Portal boundary

`PortalAdapter` remains an optional employee directory and organization/profile import source. It
is not an authentication source in the final `LOCAL_ONLY` release. Directory sync may update name,
job title, organization, phone and avatar, but must never update username, password, `is_active`,
access grants or session state.

## Release boundary

- Stage 5 remains immutable at `stage-5-complete`.
- Stage 6 uses Django session authentication, an HttpOnly cookie and CSRF protection.
- No JWT or browser token storage is introduced.
- No public registration is added.
- MFA remains a later security enhancement; the data model must not prevent it.
- Messenger implementation is not part of Stage 6.

