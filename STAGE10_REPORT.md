# Stage 10 production-readiness report

Date: 2026-08-27 UTC  
Stage 9 baseline: `020d77af98f4c2741f91666b8baf5d21a908fc9b` (`stage-9-complete^{}`)  
Operationally tested implementation: `2852bdb7c1500e85fe3b9785f1a4aaf77ad87f7e`
Browser-corrected application candidate: `ef4edb0016cea73d4eb64403cd9ad3eca48d61c0`

Application-code CI: [Stage 10 CI 33061347368](https://github.com/iikallen/tandem-tvs/actions/runs/33061347368), `release-gate` PASS in 10m25s on `ef4edb0016cea73d4eb64403cd9ad3eca48d61c0`

## Decision

The repository remains **not yet eligible** for the `stage-10-complete` tag. The dedicated
300-user/30-minute and 300-WSS/15-minute runs now pass, as do post-load database profiling and the
six locally testable fault cases. External Cloudflare/origin acceptance, the tunnel fault,
operational retention evidence, the unfamiliar-operator rehearsal and customer sign-offs remain
open. The local responsive/browser-state matrix is complete; an authorized external CSP/header
sweep remains part of the Cloudflare gate. No local result below converts those external or human
gates into PASS.

`v1.0.0` was not created. Stage 11 was not started.

## Corrections made during final audit

- Restore API smoke now sends the configured production host and HTTPS proxy metadata. This closes
  the exact CI failure `Restored CSRF smoke returned HTTP 400` from run `33009909857`.
- Operational cleanup now takes the same shared PostgreSQL advisory lock as HTTP mutations, so a
  backup cannot race temporary-media deletion and produce a mismatched database/media snapshot.
- k6 now suppresses high-cardinality URL/name system tags and can join an isolated Compose
  `tunnel-edge` network, so the full profile measures the seeded release candidate without metric
  cardinality growth or an HTTPS redirect to another environment.
- The fault reconnect probe tolerates valid queued Messenger events before its `pong`; a focused
  PostgreSQL regression test covers that ordering.
- The frontend Prettier gate accepts the checkout's native line ending, allowing the same format
  contract on Windows and Linux without rewriting the repository.
- Reduced-motion mode now stops repeating spinner animation; the focused browser regression passed.
- A failed session bootstrap now renders the existing accessible error state instead of treating a
  server failure as an anonymous session.
- Ponytail Ultra Audit result: `Lean already. Ship.` No dependency or speculative abstraction was
  added.

## Automated acceptance evidence

| Gate                            | Actual result                                                                                                                                                                                                                                                                                                                                                                   |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Protected baseline              | `main` protection requires strict `release-gate`; force-push and deletion disabled. `stage-9-complete^{}` resolves to the Stage 9 baseline.                                                                                                                                                                                                                                     |
| Static and migration checks     | Ruff format/check, basedpyright, ty, Django checks and migration drift PASS.                                                                                                                                                                                                                                                                                                    |
| Dependency/security tooling     | `pip-audit`: no known vulnerabilities; npm audit: 0 vulnerabilities; Bandit high/medium gate PASS.                                                                                                                                                                                                                                                                              |
| Backend suite                   | 261 passed in 75.42s; 94.67% total coverage (required 93.49%).                                                                                                                                                                                                                                                                                                                  |
| Module coverage                 | identity 96.26%; discussions 95.20%; publications 95.77%; Messenger 96.34%; notifications 92.44%; search 94.79%.                                                                                                                                                                                                                                                                |
| Frontend suite                  | 8 files / 33 tests PASS; ESLint, TypeScript, Prettier and production Vite build PASS.                                                                                                                                                                                                                                                                                           |
| PostgreSQL/realtime integration | Stage 2-9 verifiers PASS; dedicated realtime suite 13 passed.                                                                                                                                                                                                                                                                                                                   |
| Browser acceptance              | 39 Playwright tests passed locally in 1.7m. Manual QA covered six core routes at 360/390/768/1440 (24/24 cells, no horizontal overflow), mobile/desktop navigation, keyboard focus, programmatic labels and loading/empty/403/404/5xx/degraded states. Reduced-motion and session-bootstrap regressions PASS.                                                                   |
| Production preflight            | Exact production settings, Compose rendering, services, immutable image metadata and `APP_GIT_SHA` checks PASS.                                                                                                                                                                                                                                                                 |
| Stage 10 runtime                | Production-shaped deployment seeded; media integrity PASS; `scripts/verify_stage10.py` reported `Stage 10: PASS`.                                                                                                                                                                                                                                                               |
| Load smoke                      | 8 VUs / 60s; 653/653 checks; HTTP failures 0/653; feed/detail/history/search p95 257/226/232/508ms; realtime message p95 449ms; 4/4 full WSS sessions.                                                                                                                                                                                                                          |
| 300-user mixed load             | Default five-minute ramp plus 30-minute hold; 180 portal, 90 Messenger HTTP and 30 realtime VUs; 44,960/44,960 checks; HTTP failures 0%; feed/detail/history/search p95 581/576/749/1,060ms; realtime message p95 982ms; 954/954 full realtime sessions; post-run state PASS. Raw summary: [`mixed-300-summary.json`](docs/stage10/evidence/mixed-300-summary.json).            |
| 300-WSS capacity                | 300 authenticated sockets; observed maximum 303; exactly 300 completed and 300/300 full-duration successes; realtime and monitoring failures 0%; handshake p95 233ms; post-run state PASS. Raw summary: [`wss-300-summary.json`](docs/stage10/evidence/wss-300-summary.json).                                                                                                   |
| Connection/capacity evidence    | Mixed-run PostgreSQL peak 23/400 (5.75%, 377 headroom) across 385 five-second samples; WSS-run peak 6/400; rollback and deadlock counters stayed zero. Restored post-load database: 93,345,471 bytes; representative media: 8,252 bytes.                                                                                                                                        |
| Post-load query profiling       | All required `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` families ran against 1,000 users / 20,975 messages. Slowest measured plan was analytics at 184.554ms; global-search messages 86.713ms; all others below 25ms; `autovacuum=on`; no speculative index added.                                                                                                                   |
| Local fault recovery            | Exact-SHA isolated matrix PASS for Redis, Celery worker, Celery beat, backend, frontend and PostgreSQL. Each case rechecked committed-data digests, media integrity, durable session policy, search, outbox reconciliation, duplicate prevention and realtime reconnect. Cloudflared was explicitly skipped for the required Access-authorized external exercise.               |
| Live media read-only recovery   | Isolated media volume changed from `0755` to `0555`: application write failed with `Permission denied` and readiness returned 503. Restoring `0755` returned readiness 200 and `verify_media_integrity` PASS.                                                                                                                                                                   |
| External edge precheck          | Anonymous HTTPS reached Cloudflare Access and returned its login challenge before origin content. DNS resolved only to Cloudflare addresses; TLS 1.3 used a valid `chatlink.kz` certificate expiring 2026-11-17. The exact-SHA local Compose published no origin ports. This is not proof of the named tunnel, authenticated HTTP/WSS, or outside-network origin-bypass denial. |
| Backup/restore                  | Development-shaped and production-shaped drills PASS: lock refusal, production-target refusal, non-empty-target refusal, SHA/archive verification, isolated PostgreSQL restore, protected-media restore, media integrity and application/API smoke.                                                                                                                             |
| Final diff security review      | Codex Security scan `13c6a35e-3325-4a62-93d2-1f14ce11caee`: 134/134 changed-file receipts, eight security surfaces, zero findings. The small follow-up diff was separately static-reviewed and exercised by the green CI candidate.                                                                                                                                             |

Local supplemental checks on Windows used `uv run python -m ...` where Application Control blocked
generated console launchers. Docker Desktop supplied the isolated production-shaped load, WSS,
fault and post-load profiling evidence above; CI remains authoritative for the repository-wide
release gate on each pushed SHA.

## Operational gates still required

| Release gate                                                    | Status / required evidence                                                                                                                                                                                                                           |
| --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 300 mixed users for at least 30 minutes                         | `PASS`: default 5m ramp + 30m hold, 300 max VUs, all thresholds green, post-run state PASS; raw summary retained.                                                                                                                                    |
| 300 authenticated WSS for at least 15 minutes                   | `PASS`: 303 observed, exactly 300 completed, 300/300 full-duration, all thresholds green; raw summary retained.                                                                                                                                      |
| PostgreSQL connection budget and query plans under release load | `PASS`: peak 23/400, 377 headroom, zero rollbacks/deadlocks; required post-load plans captured, autovacuum on, no measured need for another index.                                                                                                   |
| Complete fault matrix                                           | `PARTIAL`: Redis, worker, beat, backend, frontend and PostgreSQL PASS locally; cloudflared remains the required Access-authorized external fault.                                                                                                    |
| External Cloudflare acceptance                                  | `PARTIAL`: anonymous Access interception, Cloudflare DNS and valid TLS 1.3 certificate observed; named tunnel, authenticated HTTP/WSS, full headers and outside-network direct-origin bypass denial remain pending.                                  |
| Manual responsive/accessibility review                          | `PASS` locally: 24/24 core route/viewport cells, no overflow, keyboard focus and accessible names checked; reduced motion and loading/empty/403/404/5xx/degraded states exercised. Authorized external CSP/header review remains tracked separately. |
| Backup operations                                               | `OPS_DEPENDENT`: corporate separate mount, encryption/access control, daily schedule and at least 14 retained successful days.                                                                                                                       |
| Availability/alert routing                                      | `OPS_DEPENDENT`: alert delivery exercise and the customer-defined post-go-live 99% observation period.                                                                                                                                               |
| Retention/legal hold and optional SMTP/Web Push                 | `OPS_DEPENDENT`: customer approvals and infrastructure.                                                                                                                                                                                              |
| Sign-off                                                        | `PENDING`: independent security reviewer, operations and product/customer technical acceptance.                                                                                                                                                      |

## Release sequence

1. Keep protected PR [#8](https://github.com/iikallen/tandem-tvs/pull/8) from `stage-10-production-readiness` to `main` green on its exact head.
2. Complete the operational gates above and attach sanitized evidence.
3. Merge only with a green `release-gate` on the exact PR head.
4. Confirm the post-merge `release-gate` on the exact merge SHA.
5. Only then create immutable annotated `stage-10-complete` on that merge SHA and verify its peeled
   target. Do not move Stage 1-9 tags.
