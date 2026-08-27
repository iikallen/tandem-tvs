# Stage 10 final acceptance

Stage 10 is the final implementation stage of the current TZ. This checklist records release eligibility; it does not predict results. Current decision: **IMPLEMENTATION CANDIDATE GREEN — OPERATIONAL ACCEPTANCE PENDING**. Actual evidence is recorded in [`../../STAGE10_REPORT.md`](../../STAGE10_REPORT.md).

## Product and regression gate

| Gate                                                   | Actual                                                                       |
| ------------------------------------------------------ | ---------------------------------------------------------------------------- |
| Exact baseline/tag/protected branch verified           | `PASS` — protected `main`, strict `release-gate`, immutable Stage 9 baseline |
| Full TZ traceability has no unexplained omission       | `PASS` — every requirement is mapped and open acceptance is explicit         |
| Stage 2-9 verifiers green                              | `PASS` — CI `33061347368`                                                    |
| Backend tests/coverage >=93.49% and module floors      | `PASS` — 261 tests, 94.67% total, all module floors                          |
| Frontend format/lint/typecheck/Vitest/build/audit      | `PASS` — 33 tests, build, 0 npm vulnerabilities                              |
| Playwright full suite and responsive/a11y states       | `PASS` — 39-test local suite plus 24/24 manual viewport/route cells          |
| Migration drift, Ruff, basedpyright, ty, Django checks | `PASS`                                                                       |
| pip/npm audit and Bandit                               | `PASS`                                                                       |
| Exact `make prod` after final fixes                    | `PASS` — CI `33061347368` on `ef4edb0016cea73d4eb64403cd9ad3eca48d61c0`      |

## Production and operations gate

| Gate                                                              | Actual                                                                                               |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Production-only Compose/fail-fast settings                        | `PASS`                                                                                               |
| One-shot migrations and all services healthy                      | `PASS` — production-shaped CI deployment                                                             |
| Safe SPA headers and CSP browser review                           | `PARTIAL` — automated header/CSP gate PASS; authorized browser sweep pending                         |
| Exact version/SHA in runtime and image labels                     | `PASS`                                                                                               |
| DB+media backup and isolated restore drill                        | `PASS` — both CI deployment shapes                                                                   |
| Media integrity, operational cleanup boundaries                   | `PASS` — automated scope                                                                             |
| Health/metrics privacy and alert exercise                         | `PARTIAL` — automated privacy/rule checks PASS; customer alert delivery exercise pending             |
| 300 concurrent users / 30 min thresholds                          | `PASS` — default profile, 44,960/44,960 checks, all HTTP/realtime thresholds green                   |
| 300 authenticated WSS / 15 min thresholds                         | `PASS` — max observed 303, completed 300, full-duration 300/300, failures 0                          |
| PostgreSQL query plans and connection budget                      | `PASS` — post-load plans captured; peak 23/400; rollback/deadlock 0; autovacuum on                   |
| Redis/worker/beat/backend/frontend/tunnel/PostgreSQL fault matrix | `PARTIAL` — six local cases PASS; Access-authorized tunnel fault pending                             |
| Named tunnel `tandem-tvs`, Access and no origin bypass            | `PARTIAL` — Access/DNS/TLS precheck passed; authorized tunnel/WSS and external bypass checks pending |
| Permission matrix and Platform Admin private-chat denial          | `PASS` — automated matrix; live load authorization gate pending                                      |
| Independent review: 0 Critical/High/Major                         | `PARTIAL` — diff scan found 0; independent reviewer sign-off pending                                 |

## Acceptance facts that remain operational

- 99% availability is measured after go-live over the customer-defined observation period. Stage 10 accepts monitoring/recovery controls, not an invented long-term result.
- Daily backups, >=14-day retention, backup encryption/access and on-call routing require the customer's operational platform.
- Business-data retention periods, legal hold and private-chat investigation rules require customer approval.
- Web Push remains disabled until its browser-vendor metadata boundary is approved; SMTP/malware scanning depend on customer infrastructure.

These are tracked as `OPS_DEPENDENT` in [`01-tz-traceability.md`](01-tz-traceability.md), not silently converted to PASS.

## Release sequence

1. Update `STAGE10_REPORT.md` with actual commands, counts, timings, faults, external and security evidence only.
2. Push `stage-10-production-readiness` and open a PR to protected `main`.
3. Merge only after the PR `release-gate` is green and required protections apply.
4. Confirm the post-merge `release-gate` is green on the exact merge SHA.
5. Create immutable annotated `stage-10-complete` on that exact SHA and verify the peeled tag target.
6. Do not move `stage-1-complete` ... `stage-9-complete`.

## Sign-off

| Sign-off                                        | Name / UTC / decision |
| ----------------------------------------------- | --------------------- |
| Engineering                                     | `PENDING`             |
| Independent security reviewer                   | `PENDING`             |
| Operations                                      | `PENDING`             |
| Product/customer technical acceptance           | `PENDING`             |
| Exact merge SHA                                 | `PENDING`             |
| Exact post-merge CI run                         | `PENDING`             |
| `stage-10-complete` annotated tag object/target | `PENDING`             |

`v1.0.0` is not created by Stage 10. It requires separate formal customer acceptance. No Stage 11 begins automatically; new work requires a new approved business scope.
