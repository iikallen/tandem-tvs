# Stage 9 architecture

## Messenger carryovers

Messenger now has three explicit conversation types: `DIRECT`, `GROUP` and `CHANNEL`.
Channel posts are limited to `WRITER` and `ADMIN` memberships. Ordinary members may create
`DISCUSSION` messages only while the channel discussion switch is enabled. These policies are
enforced by the service layer; a platform administrator does not gain implicit conversation
access.

Mentions are explicit `MessageMention` rows. `@all` expands only to active memberships, is rejected
for direct conversations and is limited to 10 accepted requests per user per hour. Message search
starts with the caller's membership-interval queryset and then applies text, author, date and
attachment filters. The context endpoint returns a bounded window around one authorized message.
Internal publication previews resolve Tandem publication IDs only and never fetch arbitrary URLs.

## Unified notifications

The common `notifications` app owns the seven notification types: `NEW_PUBLICATION`,
`ACK_REQUIRED`, `COMMENT_REPLY`, `COMMENT_MENTION`, `NEW_MESSAGE`, `MESSAGE_MENTION` and
`CHAT_ADDED`. Source transactions write a minimal `FanoutEvent` in PostgreSQL. Celery claims and
processes events idempotently, while a conditional unique constraint protects one unread group per
recipient and dedupe key.

Unread `NEW_MESSAGE` events group by recipient and conversation. A mention uses a separate,
higher-signal group and does not create a duplicate generic external delivery. Reading a group
closes it; a later event starts a new group. REST is authoritative. WebSocket events contain only
IDs, versions and unread counts and are hints that make other devices refetch.

Global, per-event and per-conversation preferences are evaluated by the backend during fanout.
Conversation modes are `ALL`, `MENTIONS` and `NONE`; `muted_until` is an additional temporary
suppression. An invisible external-only delivery is possible without exposing the record in the
in-app inbox.

## Search

`GET /api/v1/search` returns bounded publication, comment, message, file and employee sections, or
a cursor-paginated scoped result. Every section constructs the caller-authorized queryset before
adding vectors, rank, snippets or counts. Exact target endpoints reauthorize independently.

Russian uses `pg_catalog.russian`. Kazakh uses the pinned vendored Hunspell dictionary and a
separate PostgreSQL text-search configuration. The application combines the two independent ranks;
it does not use one language as the other's fallback. GIN indexes cover searchable domain text and
`pg_trgm` indexes support employee name and job-title matching.

