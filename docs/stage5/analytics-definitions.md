# Analytics definitions

For a publication and the selected period:

- `recipients`: current `PublicationRecipient` rows.
- `unique_views`: distinct recipient users with `PublicationView`.
- `views`: unique views in Stage 5; repeat opens update `last_viewed_at` but do not
  create another fact.
- `reach_percent = unique_views / recipients * 100` (0 when denominator is 0).
- `comments`: non-removed comments authored by current recipients.
- `reactions`: reaction rows on the publication and its non-removed comments.
- `unique_engaged`: distinct current recipients who commented or reacted.
- `engagement_percent = unique_engaged / recipients * 100`.
- `acknowledged`: current recipients with an acknowledgement.
- `acknowledgement_percent = acknowledged / recipients * 100` when required,
  otherwise null.

Percentages are decimal values rounded half-up to one decimal. Department rows
use the org-unit name stored in the recipient snapshot, so later portal changes
cannot rewrite historical identity. Category rows group publications by category
at query time. Editors see all editorial publications; authors without editor
role see only publications they authored.

Acceptance fixture: recipients 10, unique views 7, unique engaged 5 and
acknowledged 6 must yield exactly 70.0%, 50.0% and 60.0%.
