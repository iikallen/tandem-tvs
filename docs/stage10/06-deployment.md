# Stage 10 deployment acceptance

Execute [`deployment.md`](deployment.md) on the production-shaped host. Bare `compose.yaml`, mutable `latest`, dirty Git state, hand-edited containers and repeated ad-hoc migrations are not accepted deployment paths.

| Gate | Actual |
| --- | --- |
| Exact protected-main release SHA | `PENDING` |
| Production env/config preflight | `PENDING` |
| Verified pre-deploy DB+media backup | `PENDING` |
| Immutable image labels/tags | `PENDING` |
| One-shot migration success | `PENDING` |
| All services healthy | `PENDING` |
| Auth/feed/Messenger/WSS/search/notification smoke | `PENDING` |
| Backlogs/metrics/media integrity | `PENDING` |
| Cloudflare Access/Tunnel/origin isolation | `PENDING` |

Acceptance requires recorded commands, UTC interval and actual output in the final report.
