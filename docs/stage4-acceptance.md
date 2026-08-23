# Stage 4 acceptance matrix

| Area | Required evidence |
| --- | --- |
| Lifecycle | Every allowed transition succeeds; every forbidden transition fails without partial state; archive is terminal except duplicate. |
| Permissions | Author is limited to owned drafts/unpublished items and review submission; editor/admin controls every publication and all privileged actions. |
| Autosave | Browser debounce is 2–3 seconds; saves survive reload; stale `expected_revision` returns 409 with compare/reload UI. |
| Versions | Lifecycle/manual snapshots are immutable and ordered; autosave snapshots coalesce to at most one per minute per actor; hashes match canonical snapshots. |
| Scheduler | A publication scheduled about 30 seconds ahead appears within 60 seconds, including after backend/worker/beat restart; expiry removes it within 60 seconds. |
| Pinning | At most five published items occupy unique slots; regular feed excludes them; unpublish/expiry/archive auto-unpins. |
| Audience | Company-wide, exact unit, unit subtree, stable position group, named employees, and combinations are server-enforced; direct outsider access is 404. |
| Taxonomy | Editor/admin can create and patch/deactivate categories and tags; inactive taxonomy cannot be assigned to new/updated material. |
| Media | One asset is reusable; storage keys are random; extension/MIME/size/image checks reject unsafe files; original names never become paths. |
| Protected delivery | Editors can fetch assets; addressed employees can fetch assets used by visible publications; outsiders and unrelated employees receive 404; Nginx internal path is not public. |
| Rich text | Tables, protected images, internal video, attachments, and cover work; JSON contains asset IDs and no arbitrary media URL/iframe. |
| Duplicate | Content, taxonomy, audience, and media references copy to a new actor-owned draft; lifecycle, pin, views, comments, reactions, and audit do not copy. |
| Editorial UI | Publication status tabs, review queue, media library, taxonomy, versions, preview, actions, empty/loading/error/conflict states work at 360/390/768/1440. |
| Regression | Stage 2 and Stage 3 acceptance and all prior tests remain green. |
| Operations | Compose has healthy backend/worker/beat and persistent media; Redis recovery and worker/beat restart recovery pass; only Nginx binds loopback/public ingress. |
| Release | `make prod`, clean CI, external Cloudflare checks, and independent review are green; zero Critical/Major findings; `STAGE4_REPORT.md` is factual. |

## `verify_stage4.py` minimum scenario

The script must run against PostgreSQL, Redis/Celery, and the mounted filesystem. It creates
author, editor, addressed employee, and outsider contexts; exercises every lifecycle and
permission boundary; creates an actual scheduled publication around 30 seconds in the future;
survives service restarts performed by the acceptance harness; checks publication and expiry
within 60 seconds; verifies versions, conflict handling, subtree and position-group audience,
pin slots, safe upload and protected delivery, media reuse, duplication, and outsider 404s.

