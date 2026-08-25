# Stage 6 authentication architecture

## Request path

```text
Browser -> HTTPS/Cloudflare -> Nginx -> Django SessionAuthentication
                                      -> PostgreSQL database session
                                      -> Redis application cache / auth rate limits
```

The browser receives `__Host-tandem_session` in production. JavaScript never reads the cookie and
never stores a bearer token. Unsafe API calls send the current masked CSRF token in
`X-CSRFToken`. A successful login rotates both the session and CSRF token.

## Identity and authorization

`identity.User` is the sole account. `portal_id` is an optional immutable external directory
reference; `username` is the normalized local credential identifier. `AccessGrant` stores a unique
`(user, module, role)` tuple for `PLATFORM`, `NEWS` and `MESSENGER`.

Central permission helpers and DRF permission classes are the only authorization source. Legacy
`module_roles` remains temporarily for migration compatibility but is not consulted after Stage 6.

## Account lifecycle

Existing users keep unusable passwords and therefore remain pending activation. A platform admin
creates an invitation; only the SHA-256 token hash is stored. Activation sets the user's own
password, marks the invitation used and records an audit event in one transaction. Password reset
uses the same one-use hashed-token pattern. Accounts are disabled rather than deleted.

## Realtime

The existing Stage 3/5 one-time Redis ticket and WebSocket protocol remain unchanged. Only the
ticket-issuing HTTP request changes from portal evidence to the authenticated Django session.
