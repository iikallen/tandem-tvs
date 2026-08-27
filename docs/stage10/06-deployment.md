# Stage 10 deployment acceptance

Execute [`deployment.md`](deployment.md) on the production-shaped host. Bare `compose.yaml`, mutable `latest`, dirty Git state, hand-edited containers and repeated ad-hoc migrations are not accepted deployment paths.

| Gate                                              | Actual                                                                                                           |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Exact protected-main release SHA                  | `PENDING`                                                                                                        |
| Production env/config preflight                   | `PASS` — release-gate and local production-shaped deployment                                                     |
| Verified pre-deploy DB+media backup               | `PASS` — isolated production-shaped restore drill                                                                |
| Immutable image labels/tags                       | `PASS` — exact SHA labels/tags verified                                                                          |
| One-shot migration success                        | `PASS` — migration completed before backend start                                                                |
| All services healthy                              | `PASS` — exact-SHA local stack                                                                                   |
| Auth/feed/Messenger/WSS/search/notification smoke | `PASS` — smoke plus post-load state verifier                                                                     |
| Backlogs/metrics/media integrity                  | `PASS` — Stage 10 verifier and fault matrix                                                                      |
| Cloudflare Access/Tunnel/origin isolation         | `PARTIAL` — Access/TLS/DNS edge precheck passed; authorized tunnel/WSS and outside-network bypass checks pending |

Acceptance requires recorded commands, UTC interval and actual output in the final report.
