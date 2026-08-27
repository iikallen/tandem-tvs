# Stage 10 production-readiness report

Date: 2026-08-27 UTC  
Stage 9 baseline: `020d77af98f4c2741f91666b8baf5d21a908fc9b` (`stage-9-complete^{}`)  
Verified implementation candidate: `135029ea94d6aa7bb7390be7c1950788007ce508`  
CI: [Stage 10 CI 33037413497](https://github.com/iikallen/tandem-tvs/actions/runs/33037413497), `release-gate` PASS in 10m15s

## Decision

The repository is ready for a protected pull request. It is **not yet eligible** for the
`stage-10-complete` tag: the dedicated 300-user/30-minute run, 300-WSS/15-minute run, full fault
matrix, external Cloudflare/origin acceptance, operational retention evidence and customer
sign-offs have not been executed. No result below converts those operational gates into PASS.

`v1.0.0` was not created. Stage 11 was not started.

## Corrections made during final audit

- Restore API smoke now sends the configured production host and HTTPS proxy metadata. This closes
  the exact CI failure `Restored CSRF smoke returned HTTP 400` from run `33009909857`.
- Operational cleanup now takes the same shared PostgreSQL advisory lock as HTTP mutations, so a
  backup cannot race temporary-media deletion and produce a mismatched database/media snapshot.
- The frontend Prettier gate accepts the checkout's native line ending, allowing the same format
  contract on Windows and Linux without rewriting the repository.
- Ponytail Ultra Audit result: `Lean already. Ship.` No dependency or speculative abstraction was
  added.

## Automated acceptance evidence

| Gate | Actual result |
| --- | --- |
| Protected baseline | `main` protection requires strict `release-gate`; force-push and deletion disabled. `stage-9-complete^{}` resolves to the Stage 9 baseline. |
| Static and migration checks | Ruff format/check, basedpyright, ty, Django checks and migration drift PASS. |
| Dependency/security tooling | `pip-audit`: no known vulnerabilities; npm audit: 0 vulnerabilities; Bandit high/medium gate PASS. |
| Backend suite | 261 passed in 75.42s; 94.67% total coverage (required 93.49%). |
| Module coverage | identity 96.26%; discussions 95.20%; publications 95.77%; Messenger 96.34%; notifications 92.44%; search 94.79%. |
| Frontend suite | 8 files / 32 tests PASS; ESLint, TypeScript, Prettier and production Vite build PASS. |
| PostgreSQL/realtime integration | Stage 2-9 verifiers PASS; dedicated realtime suite 13 passed. |
| Browser acceptance | 38 Playwright tests passed in 1.2m. |
| Production preflight | Exact production settings, Compose rendering, services, immutable image metadata and `APP_GIT_SHA` checks PASS. |
| Stage 10 runtime | Production-shaped deployment seeded; media integrity PASS; `scripts/verify_stage10.py` reported `Stage 10: PASS`. |
| Load smoke | 8 VUs / 60s; 745 checks; HTTP failures 0/745; aggregate HTTP p95 170.49ms; realtime failures 0/4; realtime p95 287.5ms. This is smoke evidence only. |
| Backup/restore | Development-shaped and production-shaped drills PASS: lock refusal, production-target refusal, non-empty-target refusal, SHA/archive verification, isolated PostgreSQL restore, protected-media restore, media integrity and application/API smoke. |
| Final diff security review | Codex Security scan `13c6a35e-3325-4a62-93d2-1f14ce11caee`: 134/134 changed-file receipts, eight security surfaces, zero findings. The small follow-up diff was separately static-reviewed and exercised by the green CI candidate. |

Local supplemental checks on Windows used `uv run python -m ...` because Application Control blocks
generated console launchers. Backend static/audit checks and the focused cleanup-lock regression
passed; frontend lint/typecheck/audit, 32 tests and build passed. Local Docker evidence was not used:
Docker Desktop 4.84 failed before engine startup on inaccessible AF_UNIX runtime sockets. CI supplied
the authoritative Docker evidence above.

## Operational gates still required

| Release gate | Status / required evidence |
| --- | --- |
| 300 mixed users for at least 30 minutes | `PENDING`: run the default `make load-full` profile against the production-shaped release candidate and retain the k6 summary plus host/DB/Redis metrics. |
| 300 authenticated WSS for at least 15 minutes | `PENDING`: run `make load-websocket`; prove 300 observed sockets, 300 completed sessions and threshold compliance. |
| PostgreSQL connection budget and query plans under release load | `PENDING`: capture actual peak connections/headroom and compare the recorded plans after the full run. |
| Complete fault matrix | `PENDING`: execute PostgreSQL, Redis, backend, frontend, worker, beat and tunnel cases; record recovery time and durable mutation reconciliation. |
| External Cloudflare acceptance | `PENDING`: Access interception, named tunnel, TLS/headers, external HTTP/WSS and direct-origin bypass denial from outside the origin network. |
| Manual responsive/accessibility review | `PENDING`: 360/390/768/1440, keyboard-only, labels/screen reader, reduced motion and loading/empty/403/404/500/degraded states. |
| Backup operations | `OPS_DEPENDENT`: corporate separate mount, encryption/access control, daily schedule and at least 14 retained successful days. |
| Availability/alert routing | `OPS_DEPENDENT`: alert delivery exercise and the customer-defined post-go-live 99% observation period. |
| Retention/legal hold and optional SMTP/Web Push | `OPS_DEPENDENT`: customer approvals and infrastructure. |
| Sign-off | `PENDING`: independent security reviewer, operations and product/customer technical acceptance. |

## Release sequence

1. Open the protected pull request from `stage-10-production-readiness` to `main`.
2. Complete the operational gates above and attach sanitized evidence.
3. Merge only with a green `release-gate` on the exact PR head.
4. Confirm the post-merge `release-gate` on the exact merge SHA.
5. Only then create immutable annotated `stage-10-complete` on that merge SHA and verify its peeled
   target. Do not move Stage 1-9 tags.

