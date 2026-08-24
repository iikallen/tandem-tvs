# Stage 5 acceptance

Stage 5 passes only when each item has automated evidence and the full release
gate is green.

## Functional

- Two-level threaded display preserves exact reply context, stable root/reply
  cursors, recent/popular ordering and bounded previews.
- Comment create, edit, delete, attachments, mentions and reactions obey server
  policy, time windows, audience and restriction rules.
- Mention/reply notifications are deduplicated and caller-owned.
- Publication/comment reactions support the enabled five-type vocabulary with
  one user/target row and race-safe updates.
- Reports, stop-word flags, queue, hide/restore/remove, tombstones and timed user
  restrictions work and create immutable audit events.
- Recipient snapshots match publication visibility. Required acknowledgement is
  eligible-only, idempotent and irreversible; exact acknowledged/pending lists
  and CSV agree.
- Analytics return exact documented formulas, department/category rows and CSV.
- Realtime v2 hints reconcile comments, reactions and moderation in under two
  seconds in the two-browser E2E scenario.

## Security and UX

- Outsiders cannot infer publication, comment, attachment, reaction, report,
  acknowledgement, analytics or socket data.
- Hidden/removed content and reporter identities do not leak.
- CSV formula injection, cross-publication parents, invalid mentions, disabled
  types and duplicate/racing writes are rejected safely.
- New UI works by keyboard and at 360, 390, 768 and 1440 px; all production
  strings use shared i18n and controls have accessible names.

## Release evidence

Run from clean Compose: Stage 2, 3 and two-phase Stage 4 verifiers,
`verify_stage5.py`, backend tests and coverage, frontend Vitest/build,
Playwright, production checks, HTTPS/WSS tunnel acceptance and `make prod`.
Record actual commands/counts in `STAGE5_REPORT.md`. Fix every Critical/Major
review finding, merge only through a green protected PR, then create the
immutable `stage-5-complete` tag on the merged commit. Do not start Stage 6.
