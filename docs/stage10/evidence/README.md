# Stage 10 operational evidence

Captured 2026-08-27 on an isolated production-shaped Docker Compose environment.

- [`mixed-300-summary.json`](mixed-300-summary.json): runtime image revision
  `a53fa27416587f3438a1105f6683da5344070c0a`; default five-minute ramp plus 30-minute hold;
  300 max VUs; all thresholds passed; post-run state passed. The low-cardinality/system-network
  harness used for this run is committed in `2852bdb7c1500e85fe3b9785f1a4aaf77ad87f7e`;
  application HTTP/WSS code did not change between those revisions.
- [`wss-300-summary.json`](wss-300-summary.json): the same runtime and harness; 303 sockets observed,
  exactly 300 completed, and 300/300 full-duration successes.
- The complete local fault matrix ran on exact revision
  `2852bdb7c1500e85fe3b9785f1a4aaf77ad87f7e`: Redis, worker, beat, backend, frontend and
  PostgreSQL passed. Cloudflared was explicitly skipped pending an Access-authorized external
  probe.
- Five-second PostgreSQL sampling recorded mixed/WSS peaks of 23/6 connections out of 400, with
  zero rollbacks and deadlocks. Post-load state contained 1,000 users and 20,975 messages; the
  database was 93,345,471 bytes and `autovacuum=on`.

These files contain aggregate k6 metrics only. They contain no credentials, cookies, user content
or authorization headers.
