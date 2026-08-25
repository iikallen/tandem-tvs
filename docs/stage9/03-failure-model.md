# Stage 9 failure model

| Failure | Durable boundary | Expected behaviour |
| --- | --- | --- |
| Redis unavailable | Source row and fanout event are already committed in PostgreSQL | Authenticated REST and search remain available through database sessions; realtime inline delivery is skipped quickly and the outbox/fanout worker retries after recovery. |
| Worker restart | Unprocessed event/delivery stays in PostgreSQL | Idempotent claim resumes without duplicate visible notifications. |
| Backend restart | Source, notification and read state stay in PostgreSQL | Clients reconnect with a new one-use ticket and refetch REST state. |
| SMTP unavailable | Email delivery remains pending/failed independently | Messenger, News, search and in-app notifications continue; delivery retries after SMTP recovery. |
| Web Push disabled | Feature flag prevents external delivery | In-app and email policy continue unchanged. |
| Web Push returns an error | Durable delivery records the attempt | Source and in-app state remain intact; retryable failures remain recoverable. A 404/410 disables only the stale subscription. |

Redis connections use bounded one-second connect/read timeouts. Django sessions use PostgreSQL, and
the throttle cache is process-local, so an outage does not turn an otherwise authorized request
into a Redis DNS timeout. PostgreSQL remains the only durability boundary for business data,
notification fanout and external delivery state.

