# Stage 5 product reference

The TZ remains authoritative. Staffbase is used only to validate familiar interaction
patterns; it does not define the API, authorization model, or scope.

| Reference pattern | Tandem decision | Deliberate difference |
| --- | --- | --- |
| Per-post comment, reaction and acknowledgement switches | One engagement section in the existing publication editor | Every switch is enforced by the API, not only hidden in UI |
| One-time acknowledgement with totals and CSV | Idempotent acknowledgement plus acknowledged/pending lists and safe CSV | Eligibility comes from a frozen portal-recipient snapshot |
| Reported/hidden/approved/removed moderation flow | Queue with OPEN/RESOLVED reports and ACTIVE/HIDDEN/REMOVED comments | Reporter identity is never exposed to employees; original text stays only in audit/moderator responses |
| Mention autocomplete limited to post readers | Candidate lookup starts from `Publication.objects.visible_to()` | Server revalidates submitted portal IDs |
| Five simple reactions | LIKE, CELEBRATE, SUPPORT, INSIGHTFUL and THANKS | Admin enables types without a schema change; one row per user and target |
| News metrics and export | Exact recipient, unique-view, engagement and acknowledgement formulas | No inferred visits, tracking cookies, or external BI warehouse |

Sources reviewed: Staffbase post settings, acknowledgements, comment moderation,
mentions, reactions, reported comments, Studio comments, news analytics and post
statistics support pages. UI wording and visuals remain Tandem/UI Kit v2.

Explicitly excluded: Messenger, message moderation, push/email delivery,
notification preferences, campaigns, sentiment/AI, polls, personalized feed, global
search and a data warehouse.
