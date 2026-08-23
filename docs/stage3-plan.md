# Stage 3 plan — discussions, reactions, realtime

Stage 3 delivers one production vertical slice on top of the immutable `stage-2-complete`
baseline. PostgreSQL remains the source of truth; REST performs every mutation; WebSocket
events are read-only hints that cause React Query reconciliation; Redis transports events and
stores short-lived one-time tickets.

## Delivery order

1. Close Stage 2 hardening: all visible strings in i18n, explicit non-default audience and
   multi-target editor, PostgreSQL acceptance in CI, and one live browser-to-Django-to-Postgres
   test.
2. Add the isolated `discussions` domain and its visibility boundary.
3. Add comments, `LIKE`, real counters, throttles and limits.
4. Add Channels, Redis DB 1, one-time scoped tickets, origin validation and `/ws/` proxying.
5. Add the detail-page discussion/reaction UI and reconnecting reconciliation hook.
6. Prove unit, PostgreSQL/Redis acceptance, live E2E, external Cloudflare HTTP/WSS and security
   review. Record only factual results in `STAGE3_REPORT.md`.

Stage 4 is explicitly out of scope.
