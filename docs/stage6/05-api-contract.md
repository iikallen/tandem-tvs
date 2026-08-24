# Stage 6 API contract

All unsafe requests require `X-CSRFToken`; all authenticated requests use the Django session cookie.
Errors use the existing `{error: {code, message}}` envelope.

## Public authentication

| Method | Path | Result |
| --- | --- | --- |
| GET | `/api/v1/auth/csrf` | Masked CSRF token |
| POST | `/api/v1/auth/login` | User, access grants and rotated CSRF token; generic 401 on failure |
| GET | `/api/v1/auth/session` | `{authenticated, user}`; anonymous returns `authenticated: false` |
| POST | `/api/v1/auth/password/reset/request` | Always generic 200 |
| POST | `/api/v1/auth/password/reset/confirm` | Consume reset token and set password |
| POST | `/api/v1/auth/activate` | Consume invitation and set initial password |

## Authenticated account

| Method | Path | Result |
| --- | --- | --- |
| POST | `/api/v1/auth/logout` | Flush current session |
| POST | `/api/v1/auth/password/change` | Verify current password, change it and preserve only current session |
| GET | `/api/v1/me` | Profile plus normalized access grants |

## Platform administration

All paths require `PLATFORM ADMIN`.

| Method | Path | Result |
| --- | --- | --- |
| GET/POST | `/api/v1/platform/users` | Search/list or create an inactive/pending account |
| GET/PATCH | `/api/v1/platform/users/{id}` | Read/update allowlisted profile and active state |
| PUT/DELETE | `/api/v1/platform/users/{id}/grants/{module}/{role}` | Grant/revoke a role |
| POST | `/api/v1/platform/users/{id}/invitation` | Return a one-time activation capability for delivery |
| POST | `/api/v1/platform/users/{id}/password-reset` | Return a one-time admin recovery capability |

Passwords, raw tokens, session IDs and CSRF tokens are never returned by list/detail APIs or stored
in audit metadata. There is no `/register` endpoint.

