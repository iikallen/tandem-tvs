# Data retention policy boundary

The customer owns retention periods for messages, attachments and deleted content. Until that policy is explicitly approved, Tandem deletes only bounded operational records whose terminal state is already durable elsewhere. Convenience is not authority to erase user or audit data.

## Automated operational cleanup

Celery Beat runs `ops.cleanup-operational-data` daily. Current defaults:

| Data | Eligible condition | Default | Why safe |
| --- | --- | ---: | --- |
| Django sessions | `expire_date < now` | Immediate after expiry | Authentication capability is already expired. |
| Realtime outbox | `delivered_at` older than cutoff | 7 days | Source mutation remains in PostgreSQL. |
| Notification fanout | `processed_at` older than cutoff | 7 days | Notification/delivery result remains. |
| Notification delivery attempt | terminal `SENT`, `DISABLED` or `FAILED` and old | 14 days | Source event/in-app state remains; active `PENDING` is never selected. |
| Disabled push subscription | disabled and old | 30 days | It is no longer a delivery capability. |

Settings: `OPS_REALTIME_OUTBOX_RETENTION_DAYS`, `OPS_NOTIFICATION_OUTBOX_RETENTION_DAYS`, `OPS_NOTIFICATION_DELIVERY_RETENTION_DAYS`, `OPS_DISABLED_PUSH_RETENTION_DAYS`. A production change to them requires a reviewed PR and change record.

Cleanup counts rows before deletion and deletes all selected sets in one database transaction. Alerts on oldest pending rows remain independent; cleanup never hides a pending backlog by deleting it.

## Never automatically removed without customer policy

- `AuditEvent`, Messenger audit and authentication security events;
- publication versions and `MessageRevision`;
- messages, comments and moderator tombstone bodies/history;
- acknowledgement/recipient history, moderation reports/restrictions;
- active notifications or pending delivery/fanout/outbox rows;
- publication/message/comment attachments and orphan files;
- account-authored business records when a user is disabled.

`verify_media_integrity` reports orphan files separately and fails; it does not delete them. An orphan may be evidence of a failed transaction or incomplete restore and must be investigated first.

## Account termination

Set `User.is_active=false` through the supported platform administration flow. Session/security-epoch handling denies subsequent access. Do not delete the user row as a shortcut: authorship, membership intervals, audit and message history must remain attributable according to policy.

Optional directory sync cannot reactivate/deactivate or otherwise overwrite local security state under the Stage 6 requirement amendment.

## Customer decisions required

| Decision | Owner | Value |
| --- | --- | --- |
| Message and message-revision retention | Legal/records + product | `PENDING` |
| News/comment/deleted-content retention | Legal/records + product | `PENDING` |
| Protected attachment retention and legal hold | Legal/security/storage | `PENDING` |
| Audit/security-event retention | Security/legal | `PENDING` |
| Notification history retention | Product/legal | `PENDING` |
| Backup retention beyond minimum 14 days | Operations/legal | `PENDING` |
| Investigation access procedure for private chats | Security/legal | `PENDING` |

The final policy must define trigger date, legal hold, minimum/maximum period, deletion/anonymization behavior, backup propagation, audit evidence and approver. Implement business-data deletion only after those decisions, with dry-run counts, object-level authorization, audit and restore implications reviewed.

## Operational verification

Before enabling cleanup in production, create expired and non-expired fixtures for every selected table and prove only eligible terminal rows are removed. After each run, monitor pending backlog metrics and application errors. Actual Stage 10 test/run evidence: `PENDING`.

This document does not claim compliance with P209 until the customer supplies the missing retention rules; traceability therefore marks that requirement `OPS_DEPENDENT`.
