# Stage 7.0 — Stage 6 hardening

`stage-6-complete` remains immutable. This hardening is the first commit on
`stage-7-messenger-core` and precedes Messenger domain work.

## Security generation

`User.security_epoch` is copied into every authenticated session and realtime ticket. Password
reset/change, account disable and any access-grant change increment the value. HTTP middleware
rejects stale sessions and a post-commit `user.<id>.control` event immediately closes open sockets.
This replaces the former full scan and decode of every Django session row.

Authenticated activity updates `auth_last_seen_at` at most once per 60-second checkpoint.

## Recovery

Public password-reset requests use fixed-window limits of 3 attempts per normalized email and 10
per client IP per 15 minutes. Account lookup, token issuance and SMTP delivery run in Celery; the
HTTP response is always the same immediate generic response. Production SMTP mode requires an
absolute HTTPS `AUTH_PUBLIC_BASE_URL`. Invitations are restricted to never-activated accounts and
admin reset links to activated accounts.

## Authorization and directory boundary

The database constrains valid `AccessGrant` module/role pairs. Individual publication audiences use
the local `User.id`; employee search, position-group validation and publication authorization read
the local database. `PortalAdapter` remains only an explicit import/sync source.

## Trusted client IP boundary

Internet traffic reaches Nginx only through the authenticated Cloudflare Tunnel; the frontend is
otherwise bound to loopback. Nginx accepts `CF-Connecting-IP` only when the immediate peer is on the
dedicated `tunnel-edge` network (`172.31.250.0/29`), which only `frontend` and `cloudflared` join,
and overwrites `X-Tandem-Client-IP`. Direct host requests and peers on the default application
network use their socket address even if they spoof Cloudflare headers. Backend parsing additionally
requires a valid IP address.
