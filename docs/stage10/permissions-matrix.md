# Server-side permissions matrix

This is the access contract for every API family. `Allow` always means the user is active and satisfies any object gate; knowing an integer/UUID/slug never grants access.

## Roles

| Role | Grant/membership | Scope |
| --- | --- | --- |
| Anonymous | none | Public auth bootstrap and public health/runtime only. |
| News Member | `NEWS/MEMBER` | Addressed employee news, discussion and acknowledgement. |
| Author | `NEWS/AUTHOR` | News Member plus own editorial drafts/versions/transitions allowed by lifecycle. |
| Editor | `NEWS/EDITOR` | Editorial publications, schedules, taxonomy, pins, media, acknowledgement and analytics. |
| Moderator | `NEWS/MODERATOR` | Moderation queue/actions/restrictions; does not inherit editorial privileges. |
| News Admin | `NEWS/ADMIN` | News/editorial/moderation administration. |
| Messenger Member | any MESSENGER grant | People/inbox plus only conversations and historical intervals where a membership exists. |
| Channel Writer | Messenger access + active channel `WRITER` membership | Member reads; may publish channel posts. |
| Channel Admin | Messenger access + active channel `ADMIN` membership | Channel settings/membership management and posting. |
| Platform Admin | `PLATFORM/ADMIN` | Accounts/grants/recovery only; no implicit News grant or private-conversation membership. |

Multiple grants may coexist. A row describes the named role alone; combined users receive the union only after each endpoint's object check.

Symbols below: `A` allow, `O` object/ownership/lifecycle gate, `D` deny, `P` public, `T` monitoring bearer token. Unauthorized private objects should not reveal existence; APIs use the established 403/404 contract.

## Endpoint families

| Endpoint family | Anonymous | News Member | Author | Editor | Moderator | News Admin | Messenger Member / Writer / Channel Admin | Platform Admin | Object gate |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | --- |
| `/api/v1/auth/csrf`, login, activate, reset request/confirm | P | P | P | P | P | P | P | P | Generic denial, throttles and one-use/expiring capabilities; no public registration. |
| `/api/v1/auth/session` | P | A | A | A | A | A | A | A | Anonymous gets unauthenticated state, not private user data. |
| logout/password change | D | A | A | A | A | A | A | A | Current session + CSRF; password change invalidates other sessions. |
| `/api/v1/me`, org units/position groups/employees | D | A | A | A | A | A | A | A | Active authenticated account; bounded/minimized directory data. |
| `/api/v1/platform/users*`, grants, invitation, platform reset | D | D | D | D | D | D | D | A | Platform grant only; target validation and self/last-admin invariants where applicable. |
| `/api/v1/news`, pinned, categories, detail | D | O | O | O | O | O | D unless separate NEWS grant | D unless separate NEWS grant | Active NEWS grant + publication audience/status for feed/detail. |
| Publication/comment reactions, comments/replies/mentions/report/comment-media, acknowledgement | D | O | O | O | O | O | D unless separate NEWS grant | D unless separate NEWS grant | Publication visible; discussion/policy active; own mutation windows; acknowledgement recipient. |
| News pin | D | D | D | A | D | A | D | D | Editor/admin plus published lifecycle and bounded unique slot. |
| Editorial publication list/detail/review/transition/duplicate/versions | D | D | O | A | D | A | D | D | Author sees own editorial rows; editor/admin see all; transition service enforces role/lifecycle. |
| Editorial categories/tags | D | D | A read / D mutation | A | D | A | D | D | Editor/admin mutation; taxonomy state audited. |
| Engagement settings/stop words | D | D | D | A | D | A | D | D | NEWS editor/admin only. |
| Editorial media | D | D | A | A | D | A | D | D | Non-Messenger assets; delete rejected while in use and audited. |
| Editorial recipients/acknowledgements/analytics/CSV | D | D | O | A | D | A | D | D | Author own publication; editor/admin all authorized editorial rows. |
| Moderation queue, comment actions, report resolution, restrictions | D | D | D | D | A | A | D | D | Moderator/admin grant; target state and action validation; append-only audit. |
| Business audit viewer | D | D | D | D | D | **Missing** | D | D | Mandatory module-admin read-only audit capability is not implemented; DB access is not an employee-facing permission contract. |
| File-limit/type and business-retention administration | D | D | D | D | D | **Missing** | D | D | Current file limit is env-based and type allowlist is hard-coded; customer retention decisions are still pending. |
| `/api/v1/messenger/access`, people, conversation list/direct/group | D | D | D | D | D | D | A | D unless separate MESSENGER grant | Active MESSENGER grant; candidates active with Messenger access. |
| Channel creation | D | D | D | D | D | D | Messenger admin grant only | D unless separate MESSENGER admin | Valid member/writer list. |
| Conversation detail/messages/history/context/search/read/delivered/state/attachments | D | D | D | D | D | D | O | D unless actual conversation membership + Messenger grant | Current/historical membership interval; exact message and attachment reauthorized. |
| Group/channel members, roles, leave and settings | D | D | D | D | D | D | O | D unless actual membership | Group/channel admin/creator/current-member rules; direct chats immutable. |
| Message edit/delete/reaction/pin/forward/reply | D | D | D | D | D | D | O | D unless actual membership | Visible membership interval; author time window or channel/group admin policy; referenced message visible. |
| Realtime tickets and News/Messenger/notification WebSockets | D | O | O | O | O | O | O | D unless corresponding grant/object membership | One-use hashed session-bound ticket, scope, origin, security epoch and socket limit. |
| Notifications, unread/read-all, preferences, push config/subscriptions | D | A | A | A | A | A | A | A | Only current recipient rows/subscriptions; push feature flag and vendor allowlist. |
| `/api/v1/search` | D | O | O | O | O | O | O | O only for independently granted/owned domains | Each section authorizes first; exact destination reauthorizes again. Platform role alone reveals no private chat/news. |
| `/api/v1/media/<id>/content` | D | O | O | O | O | O | O | O only through normal parent access | READY asset plus at least one currently visible publication/comment/message usage and membership interval. |
| live/ready/runtime metadata | P | P | P | P | P | P | P | P | Safe data only; no hosts/secrets/queue contents. |
| `/internal/health`, `/internal/metrics` | T | T | T | T | T | T | T | T | Role/session irrelevant; constant-time monitoring bearer token required. |
| API schema/docs when enabled | D | A | A | A | A | A | A | A | Disabled by default in production; authenticated when explicitly enabled. |

## Non-negotiable invariants

1. Platform Admin is not a private-message reader and cannot grant itself content access through the platform endpoint without an explicit MESSENGER grant and ordinary conversation membership.
2. Conversation membership intervals bound old/new history, files, search, context, reply, forward, pins and receipts.
3. Publication visibility bounds detail, comment, reaction, acknowledgement, media, notification target and search result.
4. Notification ownership never grants access to its target; navigation triggers a fresh target authorization.
5. File storage paths and `X-Accel-Redirect` are returned only after authorization; the internal Nginx path is not public.
6. React route guards and hidden controls are usability only; every allow/deny above is server-enforced.

## Automated evidence

- News/audience/media: `test_publication_api.py`, `test_publication_domain.py`, `test_stage4.py`, `test_stage5.py`.
- Auth/platform: `test_authentication.py`, `test_stage6.py`, `test_realtime.py`.
- Private Messenger/media: `test_messenger.py`, `test_stage8.py`, `test_stage9.py`.
- Notifications/search exact targets: `test_stage9.py`.

Final Stage 10 parametrized all-role sweep and live IDOR acceptance: `PENDING`. The release must keep zero authorization violations in the 300-user run and zero unresolved Critical/High/Major review findings.
