# Stage 10 k6 profiles

Seed only an isolated load environment, then supply its public URL and the same operator-owned
password to k6:

```console
TANDEM_LOAD_PASSWORD='<secret>' python manage.py seed_load_profile --confirm-load-environment
PROFILE=smoke BASE_URL=https://tandem.example TANDEM_LOAD_PASSWORD='<secret>' k6 run load/k6/stage10.js
BASE_URL=https://tandem.example TANDEM_LOAD_PASSWORD='<secret>' k6 run load/k6/stage10.js
BASE_URL=https://tandem.example TANDEM_LOAD_PASSWORD='<secret>' k6 run load/k6/websocket-capacity.js
```

`PROFILE=smoke` is 8 VUs for one minute. The full mixed profile ramps for five minutes, then holds
180 browse/search users, 90 Messenger HTTP users, and 30 realtime users for 30 minutes. The
capacity profile opens 300 authenticated sockets, each held for 900 seconds; its 895-second p95
threshold allows five seconds of scheduler/close-observation tolerance while still proving the
required 15-minute hold.

Because the sockets ramp for two minutes before all 300 are present, the earliest socket remains
open for about 17 minutes. Production enforces a server-side socket lifetime of at least 18 minutes
and defaults to 20 minutes, leaving a bounded reconnect interval while covering the acceptance
window. Session revocation and session idle/max-age checks remain independent of that lifetime.

The full HTTP profile uses a 30-second think time between complete user journeys; smoke uses one
second. Override `THINK_SECONDS` only for an explicitly documented diagnostic run.

Every portal user refreshes the feed and opens a publication. Global search is deterministically
staggered across 10% of portal iterations because it is a deliberate action, not part of every
feed refresh; the full run still records more than 1,000 search samples. `LOAD_RAMP_DURATION` and
`LOAD_HOLD_DURATION` may shorten a calibration, but release evidence always uses the five- and
thirty-minute defaults.

Set `WS_BASE_URL` only when the WebSocket origin differs from `BASE_URL`. `LOAD_USER_COUNT` and
`LOAD_USER_OFFSET` select disjoint `load-NNNN` account ranges for distributed runners.
