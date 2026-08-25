# Stage 9 notification delivery and privacy

## In-app and realtime

Notification rows and read state live in PostgreSQL. Cursor APIs expose only the current user's
rows. One-use, session-bound Stage 8 tickets protect `/ws/v1/notifications`; a notification never
grants access to its target.

## Browser push

Web Push is feature-complete behind `WEB_PUSH_ENABLED` and is disabled by default in production.
Enabling it requires VAPID keys supplied only through environment/secret management. Subscription
endpoints and authentication keys are treated as secrets and are excluded from logs and API lists.
HTTP 404/410 disables a stale subscription.

The backend accepts only configured browser-vendor host suffixes, HTTPS on the standard port, at
most five active subscriptions per user and at most 20 registration requests per hour. Production
must keep a non-empty host allowlist when Web Push is enabled.

Push payloads are generic wake-ups and contain no message/comment body, publication title, employee
name or file name. The browser fetches presentation data from authenticated Tandem APIs.

Standards-based Web Push necessarily contacts the browser vendor's push service. Encryption hides
payload content, but delivery metadata remains visible to that infrastructure. Because the source
requirements prohibit module data leaving the corporate perimeter, production enablement requires
an explicit customer security decision. Until approved, the safe production decision is
`WEB_PUSH_ENABLED=false`.

## Email

Email is asynchronous and uses configured internal SMTP. Delivery records hold retry state; an SMTP
failure cannot roll back the source event or in-app notification. Private chat mail is generic and
does not include message text. Ordinary message delivery is delayed and coalesced; acknowledgement
and inactive-user rules may elevate important events. `last_activity_at` is checkpointed at most
approximately once per five minutes instead of being written on every request.

Immediately before push or email I/O, the worker rechecks the current global, event and chat
preferences plus temporary mute state. Disabling a channel therefore suppresses already queued but
not yet sent delivery as well as future fanout.
