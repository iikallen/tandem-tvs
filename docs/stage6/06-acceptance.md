# Stage 6 acceptance

## Functional and security gates

- Existing user primary keys and Stage 1–5 data survive migration.
- Username is required, normalized and case-insensitively unique; portal ID is optional.
- Passwords are usable and Argon2id-hashed; length is 15–128 with Unicode, spaces and paste allowed.
- Login uses a generic failure, username/IP throttling, session rotation and CSRF rotation.
- Production uses only `SessionAuthentication`, cached-database sessions and secure `__Host-`
  cookie settings; injected portal headers cannot authenticate.
- Absolute/idle expiry, logout, inactive-account denial and password-change session invalidation pass.
- Invitations and resets are random, hash-only, expiring and one-use; unknown reset email is generic.
- AccessGrant is the authorization source for all News/editorial/moderation paths and represents
  Messenger entitlement without implementing Messenger.
- Platform user management cannot be used by an ordinary employee and cannot mass-assign password,
  active status or grants.
- Local sessions can issue existing realtime tickets; anonymous/expired sessions cannot.
- Redis and backend restarts preserve a cached-database session.
- Login, activation, reset and user-management UI are accessible, localized and responsive at
  360, 390, 768 and 1440 pixels.

## Release gate

From clean volumes: no-cache build, migrations, Stage 2–6 verifiers, full backend suite with overall
coverage not below 93.14% and identity/auth coverage at least 95%, frontend formatting/lint/typecheck,
Vitest, build, audits and Playwright. Verify Cloudflare HTTPS/Access/WSS. Perform a separate security
review, fix every Critical/Major finding, rerun `make prod`, merge through protected `main`, confirm
green post-merge CI and then create `stage-6-complete`. Messenger must not start.

