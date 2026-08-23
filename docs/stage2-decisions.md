# Stage 2 decisions

This log fixes the decisions needed to implement the Stage 2 vertical slice without
expanding into later stages. A decision may be revised only with a documented reason and
matching test changes.

## Foundation decisions made in Phase 2.0

### D2-001 — Stage 1 is an immutable release baseline

Stage 2 branches from the commit and tag recorded in `docs/stage2-plan.md`. Existing identity,
portal adapter, and organization models are extended only where a demonstrated Stage 2 need
requires it; they are not recreated.

### D2-002 — Directory search is a bounded data-minimization API

Employee search does not enumerate on an empty or one-character query. Queries are trimmed,
limited to 100 characters, and capped at 20 results at both the API and adapter boundary.
Only `portal_id`, `full_name`, `job_title`, and `org_unit_external_id` are returned. Email,
phone, avatar URL, and roles are not part of this lookup response.

### D2-003 — Personalized API responses are non-cacheable

Every authenticated, user-specific API view must inherit `PrivateAPIView` or provide an
equivalent tested policy. Its response includes `Cache-Control: private, no-store,
max-age=0`. Public liveness/readiness/runtime metadata remain separate.

### D2-004 — Interactive API documentation is not a production surface

Production registers neither `/api/schema` nor `/api/docs`. Development and tests may enable
them, but portal authentication is still required. Swagger assets are supplied by the exact
locked `drf-spectacular-sidecar` package and are never loaded from a floating CDN URL.

### D2-005 — Portal organization listing is an authoritative snapshot

An organization sync transaction upserts every returned unit and soft-deactivates every
local unit omitted from the snapshot. It never deletes a projection, so existing foreign
keys and audit history remain valid. A later snapshot may reactivate a unit. Inactive units
are excluded from selectors and can never grant audience access.

This assumes that `PortalAdapter.list_org_units()` returns a complete snapshot. A real portal
adapter with delta semantics must normalize deltas into a complete snapshot or introduce a
separate, explicitly tested sync operation before it replaces the placeholder adapter.

### D2-006 — Application containers run least-privileged

Backend and frontend run as fixed non-root users with read-only root filesystems. Writable
paths are explicit temporary mounts. Capabilities are dropped; Nginx retains only the bind
capability required for its established port 80 contract. `no-new-privileges` applies to
application and tunnel containers. PostgreSQL and Redis keep their upstream runtime model in
Phase 2.0 to avoid untested changes to persistence.

## Decisions that govern publication implementation

### D2-007 — Audience rules are a union

A published publication is visible when at least one active audience rule matches the active
user. Rules of the same or different types therefore combine with logical OR. `ALL` is
exclusive: when selected, no narrower rule may be stored because it would be redundant and
misleading.

- `EMPLOYEE` matches an exact immutable `User.portal_id`.
- `ORG_UNIT` matches the user's exact active `OrgUnit.external_id`; descendants are not
  implied in Stage 2.
- `MODULE_ROLE` matches an exact value in the user's portal-projected `module_roles`.
- no rule, an inactive target, a draft, or an inactive user grants no employee access.

Audience mutations go through one transactionally locked replacement service. It removes
duplicates, rejects inactive targets, and enforces the exclusivity of `ALL` before replacing
the stored union. Organization and employee foreign keys use the immutable portal-facing
`external_id` and `portal_id` values rather than local surrogate IDs.

Exact-unit matching avoids silently guessing portal hierarchy policy. If subtree targeting is
required later, it must become an explicit rule option with tests rather than changing the
meaning of stored rules.

### D2-008 — Visibility is a queryset boundary

`PublicationQuerySet.visible_to(user)` is the canonical employee authorization primitive.
Feed, detail, search, unread, and view tracking start from it. An unauthorized publication is
reported as not found so direct URLs do not reveal its existence. Frontend filtering is never
an authorization control.

Editorial querysets are separate and protected by explicit server-side editor/administrator
permissions.

### D2-009 — Rich text is structured and validated

Publication body content is stored as validated ProseMirror-compatible JSON. Stage 2 accepts
only the nodes and marks exposed by its limited toolbar. Arbitrary HTML, scriptable markup,
unknown nodes, and unsafe URL schemes are rejected server-side. Rendering consumes the
structured document and does not use raw `dangerouslySetInnerHTML`.

The persisted Stage 2 whitelist is paragraph, H2, H3, bold, italic, bullet list, ordered
list, blockquote, hard break, and safe link. Documents are bounded to 5,000 nodes, 100,000
text characters, and nesting depth 16. Links allow HTTP(S), mail, portal-relative, and
fragment targets; new-window links require `noopener`.

A normalized plain-text representation is generated server-side for search; clients cannot
supply or override it.

### D2-010 — Minimal lifecycle with an extension-safe enum

Only `DRAFT` and `PUBLISHED` behavior is implemented. The status column uses stable string
choices so later values can be added without changing existing rows, but review, scheduling,
unpublishing, archiving, version browsing, and approval transitions remain out of scope.

### D2-011 — Views are rows, not a mutable counter

`PublicationView` has a unique constraint on `(publication, user)` and stores first/last view
times. Unique view count derives from those rows. A repeat open updates `last_viewed_at`
without increasing the unique count. This row also provides Stage 2 unread state and a safe
future basis for acknowledgement.

### D2-012 — Feed uses stable cursor pagination

The employee feed orders by `published_at DESC, id DESC`, backed by indexes, and uses cursor
pagination. Default and maximum sizes are 20 and 50. Filtering and authorization happen
before pagination so insertions cannot expose, skip, or duplicate unauthorized objects.

### D2-013 — PostgreSQL provides Stage 2 search

Search applies `visible_to(user)` first, then published status, weighted title/summary/body
vectors, rank, and pagination. Stage 2 adds no external search service. Russian/Kazakh
morphological completeness is not claimed; unified multilingual module search remains a
later stage.

### D2-014 — Editorial mutations are attributable and auditable

The server derives authorship from the authenticated user and sets publish time. Create,
update, and publish operations append immutable audit events inside the same transaction as
the mutation. Clients cannot select an author or mutate audit history.
