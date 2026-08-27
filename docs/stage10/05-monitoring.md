# Stage 10 monitoring acceptance

Operator procedure, metric contract and triage: [`monitoring.md`](monitoring.md). Alert rules: `ops/prometheus/alerts.yml`.

Required release checks:

- public live/ready/runtime endpoints reveal only safe data;
- internal health/metrics deny requests without the monitoring bearer token;
- HTTP metrics use stable route labels, never raw IDs or user/private values;
- PostgreSQL, media, Redis, Celery heartbeat, sockets, realtime/notification backlog and media integrity are observable;
- seven minimum user-impact alerts parse and fire/resolve in a non-production test;
- the customer supplies scrape routing, on-call receivers and the post-go-live 99% SLO observation definition.

| Evidence | Actual |
| --- | --- |
| Endpoint auth/privacy | `PENDING` |
| Low-cardinality metric audit | `PENDING` |
| Prometheus rule validation | `PENDING` |
| Alert fire/route/resolve exercise | `PENDING` |
| Dashboard/scrape configured | `PENDING` |
| 99% SLO observation start | `PENDING` |

Stage 10 may pass availability controls while the actual 99% SLO remains `OPS_DEPENDENT` until its observation period completes.
