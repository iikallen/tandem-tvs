# Stage 5 API contract

All endpoints require portal authentication. Publication-scoped employee APIs
resolve the publication through `visible_to(request.user)` and return 404 on an
addressing failure.

## Employee

| Method/path | Contract |
| --- | --- |
| `GET/POST /api/v1/news/{id}/comments?sort=recent|popular` | 20 root comments, each with at most two preview replies; POST accepts body, optional `reply_to`, mention portal IDs and READY media IDs |
| `GET /api/v1/news/{id}/comments/{root}/replies` | Stable cursor pages of 30 replies |
| `PATCH/DELETE /api/v1/news/{id}/comments/{comment}` | Author-only and within server-configured window |
| `GET /api/v1/news/{id}/mention-candidates?search=` | Active eligible readers only |
| `GET /api/v1/news/{id}/reactions` | Publication summary and bounded actor preview |
| `PUT/DELETE /api/v1/news/{id}/reactions/{type}` | Create/change or remove caller reaction |
| `GET /api/v1/news/{id}/comments/{comment}/reactions` | Comment summary |
| `PUT/DELETE /api/v1/news/{id}/comments/{comment}/reactions/{type}` | Create/change or remove caller reaction |
| `POST /api/v1/news/{id}/comments/{comment}/reports` | Idempotent report |
| `POST /api/v1/news/{id}/acknowledgement` | Idempotent, irreversible, only current eligible recipient when required |
| `GET /api/v1/notifications`; `POST /api/v1/notifications/{id}/read` | Caller-owned in-app notifications |

## Editorial

| Method/path | Contract |
| --- | --- |
| `GET/PATCH /api/v1/editorial/settings/engagement` | Admin settings and stop-word list |
| `GET /api/v1/editorial/moderation` | Bounded OPEN review queue |
| `POST /api/v1/editorial/moderation/comments/{id}/{hide|restore|remove}` | Explicit moderator transition |
| `POST /api/v1/editorial/moderation/reports/{id}/resolve` | Resolve report with audit |
| `POST/DELETE /api/v1/editorial/moderation/users/{portal_id}/restriction` | Restrict/revoke commenting |
| `POST /api/v1/editorial/publications/{id}/recipients/refresh` | Recompute current snapshot while retaining history |
| `GET /api/v1/editorial/publications/{id}/acknowledgements?status=acknowledged|pending` | Exact current recipient list |
| `GET .../acknowledgements.csv` | UTF-8 safe CSV |
| `GET /api/v1/editorial/publications/{id}/analytics` | Exact per-publication metrics and department rows |
| `GET /api/v1/editorial/analytics?date_from=&date_to=&category=` | Publication/category aggregate rows |
| `GET /api/v1/editorial/analytics.csv?...` | Same authorized filtered data as CSV |

Mutation errors are structured DRF 400/403 responses. Realtime v2 events contain
target IDs and event kind only; clients reconcile through REST.
