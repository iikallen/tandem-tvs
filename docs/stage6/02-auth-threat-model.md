# Stage 6 authentication threat model

## Assets and trust boundaries

Assets are password hashes, session identifiers, invitation/reset capabilities, access grants and
security audit records. Requests cross Cloudflare Access, Nginx and Django; Cloudflare Access is an
outer perimeter and never substitutes for Tandem authentication. PostgreSQL is the session source
of truth and Redis is a cache/rate-limit/realtime service.

## Threats and controls

| Threat | Required control |
| --- | --- |
| Password brute force / credential stuffing | Per-normalized-username and per-IP throttles; generic failures; security events |
| User enumeration | Identical login and reset responses for unknown users and bad credentials; dummy password hash |
| Password database compromise | Django Argon2id first; no plaintext credentials; 15–128 character policy and common-password blocklist |
| Session theft | Secure `__Host-` HttpOnly SameSite cookie, HTTPS, no token storage in browser JavaScript |
| Session fixation | Django `login()` session rotation and CSRF rotation |
| Excessive session lifetime | 12-hour absolute and 30-minute idle deadlines enforced server-side |
| CSRF | Session-backed CSRF token; CSRF on login and every unsafe mutation |
| XSS credential theft | Passwords only in native password inputs; session inaccessible to JavaScript; existing rich-text allowlist |
| Stolen invitation/reset token | 256-bit random token, SHA-256 stored, short expiry, one use, transactional consumption |
| Token brute force/replay | High-entropy token, constant lookup hash, used/expired denial, rate-limited entry points |
| Privilege escalation / mass assignment | Central role checks; allowlisted serializers; grants changed only by platform admin |
| Disabled user with active session | Django backend rejects inactive users on the next request |
| Old Portal authentication bypass | `SessionAuthentication` is the only production DRF authenticator; portal headers are ignored |
| WebSocket authentication bypass | Existing one-time ticket can only be issued by an authenticated local HTTP session |
| Admin account compromise | Explicit platform-admin grant, security events and no Django superuser product bypass |
| Secret/audit leakage | Passwords, raw tokens, session IDs and CSRF tokens are excluded from models, metadata and logs |

## Residual risks

MFA and breached-password remote lookup are deferred. MFA should be added first for platform admins,
editors and moderators. Password checking remains local so password material is never sent to an
external service.

