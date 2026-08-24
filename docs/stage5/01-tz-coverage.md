# Stage 5 TZ coverage matrix

Source of truth: `TZ_Portal_News_Messenger_v1_0.docx` v1.0. Priority follows TZ
section 0: goals → acceptance criteria → functional requirements → other material.

Statuses: `DONE`, `STAGE_5`, `DEFERRED_BY_DEPENDENCY`, `OUT_OF_SCOPE_BY_AGREEMENT`.

## 4.2 Publication

| TZ requirement | Current implementation | Status | Stage 5 implementation | Test | Acceptance evidence |
| --- | --- | --- | --- | --- | --- |
| Full content, author/date, reactions, discussion | Publication detail, rich renderer, flat comments and publication likes exist | STAGE_5 | Keep detail and replace engagement blocks with Stage 5 policies/threads/reactions | API + E2E detail flow | Stage 5 live E2E |
| Formatted headings, lists, links, quotes, tables, images, video | Structured rich-text schema and protected media exist | DONE | Regression only | Rich-text regression | Stage 4 + `make prod` |
| Downloadable attachments with size/type | Protected `MediaAsset` attachments exist | DONE | Regression only | Media authorization tests | Stage 4 verifier |
| Full-screen image gallery | Images render inline; no gallery interaction | STAGE_5 | Add accessible image dialog/gallery to publication detail | Vitest + responsive E2E | Stage 5 E2E |
| Mandatory acknowledgement and exact acknowledged/pending lists | Not implemented | STAGE_5 | Recipient snapshot, one-time acknowledgement, editor lists and CSV | Model/API/CSV/E2E | `verify_stage5.py` |
| Share publication to messenger with preview | Messenger entities do not exist | OUT_OF_SCOPE_BY_AGREEMENT | Stage 6/7 after Chat/Message exists | Future messenger acceptance | Not part of Stage 5 |
| Unique view accounting resistant to repeated opens | `PublicationView` is unique per publication/user | DONE | Use it as analytics fact | Exact metrics tests | Stage 2 regression |

## 4.3 Comments

| TZ requirement | Current implementation | Status | Stage 5 implementation | Test | Acceptance evidence |
| --- | --- | --- | --- | --- | --- |
| Visible employee can comment unless discussion is closed | Visibility enforced; no close/policy flag | STAGE_5 | `comments_enabled` enforced server-side | Policy API tests | Stage 5 E2E |
| Threaded replies with bounded depth | Comments are flat | STAGE_5 | `thread_root` + `reply_to`, two visual levels | Cross-publication/cycle/thread tests | `verify_stage5.py` |
| Author edit/delete within configured window; edited marker visible | Edit/delete unlimited; edited marker exists | STAGE_5 | Singleton settings and exact deadline checks | Before/at/after boundary tests | Backend suite |
| Mentions with notification | Not implemented | STAGE_5 | Access-filtered candidates, validated mentions, in-app notification | Candidate/notification tests | Live E2E |
| Comment image/file attachments when category permits | Not implemented | STAGE_5 | Reuse `MediaAsset`; category policy and limits | IDOR/policy/limit tests | Stage 5 E2E |
| User report enters moderation queue | Not implemented | STAGE_5 | Idempotent user reports; reporting does not auto-hide | Report/permission tests | Moderation E2E |
| Recent/popular sorting and partial long-thread loading | One cursor over all flat comments | STAGE_5 | Root cursor 20, reply cursor 30, two-reply previews | Ordering/pagination/query tests | API acceptance |
| Moderator deletion leaves placeholder; original content retained in audit | Author tombstone only | STAGE_5 | Hidden/removed tombstones with immutable audit state | Leakage/audit tests | Moderation E2E |

## 4.4 Reactions

| TZ requirement | Current implementation | Status | Stage 5 implementation | Test | Acceptance evidence |
| --- | --- | --- | --- | --- | --- |
| Like plus administrator-enabled expanded set | LIKE only | STAGE_5 | LIKE/CELEBRATE/SUPPORT/INSIGHTFUL/THANKS settings | Settings/type tests | Admin UI + E2E |
| Reactions on publications and comments | Publication only | STAGE_5 | Nullable publication/comment target with exact-one constraint | Target tests | `verify_stage5.py` |
| Count and list of reactors; repeat removes own reaction | Counts/mine exist; no actor list | STAGE_5 | Summary includes actors; PUT changes type, DELETE removes | API tests | Detail E2E |
| Realtime counter update | Publication LIKE event exists | STAGE_5 | Version 2 `reaction.changed` for both target types | Channels + two-browser test | Realtime E2E ≤2s |
| One reaction per employee per object | Current uniqueness includes type and permits several types | STAGE_5 | Conditional unique constraints and transactional upsert | Race/constraint tests | PostgreSQL acceptance |

## 4.6 Moderation and statistics

| TZ requirement | Current implementation | Status | Stage 5 implementation | Test | Acceptance evidence |
| --- | --- | --- | --- | --- | --- |
| Queue of comment reports: leave, hide, remove, restrict author | Not implemented | STAGE_5 | Moderation queue, dedicated transactional actions, reporter privacy | Role/state/leakage tests | Moderation E2E |
| Queue of message reports | Message model does not exist | DEFERRED_BY_DEPENDENCY | Add after Stage 6/7 Message implementation | Future message moderation suite | Recorded dependency |
| Close/reopen discussion per publication | Not implemented | STAGE_5 | Publication policy toggle + audit | Mutation bypass tests | Editor/employee E2E |
| Stop words flag comments for review | Not implemented | STAGE_5 | NFKC/casefold/plain-text matching; visible comment + stop-word report | Evasion/visibility tests | Moderation acceptance |
| Publication views, reach, reactions, comments, acknowledgement rate | Only raw views/comments/reactions exist | STAGE_5 | Recipient-denominator analytics with fixed formulas | Exact deterministic metrics | Analytics fixture |
| Period report by category/department and spreadsheet export | Not implemented | STAGE_5 | Scoped overview, snapshot departments, safe CSV | Scope/formula-injection tests | CSV acceptance |

## 7.2 Acceptance

| TZ requirement | Current implementation | Status | Stage 5 implementation | Test | Acceptance evidence |
| --- | --- | --- | --- | --- | --- |
| Portal SSO and blocked account denied | Implemented server-side | DONE | Regression | Authentication tests | `make prod` |
| Exact publication addressability; direct outsider link denied | Implemented | DONE | Audience resolver parity with recipient snapshot | Parity/outsider tests | Stage 2 + Stage 5 verifier |
| Scheduled publication ≤60s including restart | Implemented and measured | DONE | Regression | Stage 4 verifier | `make prod` |
| New publication appears in recipient feed ≤60s | REST/cache behavior implemented | DONE | Regression | Stage 2/live tests | `make prod` |
| Comment/reaction/counters update without reload ≤2s | Flat comment/like realtime exists | STAGE_5 | Thread, reaction, moderation v2 hints + REST reconciliation | Two-browser timing tests | Stage 5 E2E |
| Messenger delivery <1s and reconnect without loss/duplicates | Messenger not started | OUT_OF_SCOPE_BY_AGREEMENT | Stage 6/7 | Future messenger E2E | Not Stage 5 |
| Messenger unread count exact across devices | Messenger not started | OUT_OF_SCOPE_BY_AGREEMENT | Stage 6/7 | Future messenger E2E | Not Stage 5 |
| Foreign publication/chat file direct URL denied | Publication media is protected; chat missing | DONE | Extend protection to comment attachments | IDOR tests | Stage 4 + Stage 5 verifier |
| Editorial and moderation actions reconstructable from audit | Editorial audit exists; moderation missing | STAGE_5 | Reuse append-only `AuditEvent` for every moderation/admin action | Previous/new state tests | Security review |
| Exact acknowledged/pending lists | Not implemented | STAGE_5 | Snapshot-backed lists and CSV | Exact list tests | Stage 5 E2E |
| Feed/chat ≤2s at stated volume and 300 sessions | Query coverage exists; full load test is Stage 9 | OUT_OF_SCOPE_BY_AGREEMENT | Stage 5 query budgets; Stage 9 load/300 sessions | Query-count tests now | Stage 9 final load evidence |
| Mobile feed/comment/chat/file flows | Feed works; Stage 5 flows missing; chat later | STAGE_5 | Engagement/moderation/analytics at 360+; chat in Stage 6/7 | 360/390/768/1440 E2E | Stage 5 E2E |
| Restart recovery without data loss | PostgreSQL/Redis/Celery stack persists | STAGE_5 | Verify new Stage 5 state across backend/Redis restart | Real-stack verifier | `verify_stage5.py` |
| Availability ≥99% over observation period | Requires operational observation | OUT_OF_SCOPE_BY_AGREEMENT | Stage 9 production observation/runbook | Availability monitor | Stage 9 evidence |

## 8 Security and retention

| TZ requirement | Current implementation | Status | Stage 5 implementation | Test | Acceptance evidence |
| --- | --- | --- | --- | --- | --- |
| HTTPS with valid certificate | Cloudflare Tunnel + Access | DONE | Re-verify HTTPS/WSS | External probes | Cloudflare acceptance |
| Server checks rights on every data/file request | Existing visible-to and media boundary | STAGE_5 | Apply to every new endpoint and attachment path | Outsider/role tests | Security review |
| Communications/files stay in company perimeter | Self-hosted PostgreSQL/Redis/media | DONE | No external data service | Compose review | Release report |
| Uploads non-executable, safe headers, optional scanner hook | Stage 4 validation/internal Nginx delivery | DONE | Reuse for comment assets | Media regression | Stage 4/5 verifier |
| User content sanitised against unsafe markup | Plain comments + validated rich text | DONE | Keep comments plain; no regex/HTML rendering | Injection tests | Backend/frontend suite |
| Admin/editor/moderation actions audited and immutable in UI | Append-only model exists | STAGE_5 | Add Stage 5 event types/states; no mutable log API | Audit mutation tests | Review |
| Admin cannot casually read private chats | Messenger absent | OUT_OF_SCOPE_BY_AGREEMENT | Stage 6/7 privacy model | Future authorization tests | Not Stage 5 |
| Configurable retention and automatic deletion | Not implemented | OUT_OF_SCOPE_BY_AGREEMENT | Stage 9 operations/retention implementation | Retention job tests | Stage 9 |
| Terminated employee loses access; history preserved | Portal fail-closed and PROTECT relationships | DONE | Ensure snapshots/history remain, inactive access denied | Inactive-user tests | Regression |
| Daily DB/file backup, ≥2 weeks, verified restore | Infrastructure operation | OUT_OF_SCOPE_BY_AGREEMENT | Stage 9 deployment/runbook | Restore drill | Stage 9 evidence |

## Explicit Stage 5 exclusions

Messenger, browser push, email delivery, notification preferences, global search,
campaigns, sentiment AI, polls, personalized feed, Staffbase Content Reviews and an
external BI warehouse are not implemented in Stage 5. Message moderation is the only
`DEFERRED_BY_DEPENDENCY` item because a `Message` entity does not yet exist.
