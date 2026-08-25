# Ponytail ultra whole-repository audit

`delete:` Remove the unused `AuthDeliveryAdapter` protocol and test-only `ConsoleAuthDelivery`; the
password-reset task calls `SMTPAuthDelivery` directly and no runtime code selects another adapter.
Replacement: nothing. [`backend/apps/identity/delivery.py`]

`delete:` Remove the legacy optional `Conversation.members` response shape and frontend fallbacks;
the bounded inbox contract already supplies `peer` and `member_count`, while the members endpoint
owns full membership data. Replacement: those existing fields/endpoints.
[`frontend/src/shared/api/index.ts`, `frontend/src/pages/messages/MessengerAccessPage.tsx`]

net: -35 lines, -0 deps possible.

Both findings are non-release-significant cleanup. The report-only audit applied no changes. The
dependency scan found no package that can be replaced by the standard library or an already-used
native platform facility without removing a required Stage 1–9 feature.

