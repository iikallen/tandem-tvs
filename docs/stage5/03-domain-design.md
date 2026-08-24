# Stage 5 domain design

## Boundaries

PostgreSQL is the source of truth. REST owns mutations. WebSocket messages are
version-2 invalidation hints. Redis transports hints and does not hold business
state. `AuditEvent` remains the only immutable history.

Stage 5 extends the existing `publications` and `discussions` domains and adds a
small in-app notification model. It reuses `MediaAsset`, portal users, audience
rules and existing editorial roles.

## Models and invariants

- `Publication`: `comments_enabled`, `reactions_enabled`,
  `acknowledgement_required`; safe defaults are true, true, false.
- `Category`: `comment_attachments_enabled`.
- `EngagementSettings`: singleton row, edit/delete windows, enabled reaction
  types, attachment count/size. LIKE is enabled initially.
- `Comment`: root when both relation fields are null; reply stores the root in
  `thread_root` and the exact addressed comment in `reply_to`. Both must belong
  to one publication. UI depth is always two.
- `CommentMention` and `CommentAttachment`: unique links owned by a comment.
- `Reaction`: exactly one of publication/comment is set and one row exists per
  user/target. PUT creates or changes the type; DELETE removes it.
- `CommentReport`: one reporter/comment; reporting never hides content.
- `ModerationFlag`: stop-word or report-derived review signal.
- `CommentRestriction`: active until revoked or expired; comment creation is
  rejected server-side.
- `Notification`: in-app COMMENT_REPLY/COMMENT_MENTION only. Mention and reply
  to the same person create one notification.
- `PublicationRecipient`: immutable identity/org snapshot per publication and
  portal ID. A refresh marks current membership without deleting history.
- `Acknowledgement`: one irreversible row per publication and recipient.

## Audience and snapshots

The recipient resolver iterates active portal-backed users and applies the same
address predicates as `visible_to()`: ALL, active org unit/subtree, employee,
module role and active portal position group. Publishing and explicit snapshot
refresh run the resolver. Historical rows remain, while `is_current` controls
the current denominator. Tests assert resolver/visibility parity.

## Moderation and leakage rules

Employees see a neutral tombstone for HIDDEN/REMOVED comments and cannot read
their attachments. Moderators can inspect the body and audit history. Reports
do not disclose reporters outside editorial APIs. Stop words use Unicode NFKC
plus case-folded literal containment; no user-controlled regex executes.

## Metrics

See `analytics-definitions.md`. All lists are bounded and indexed. CSV cells
starting with `=`, `+`, `-` or `@` are prefixed with an apostrophe.
