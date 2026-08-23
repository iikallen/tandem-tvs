# Stage 3 decisions

## Reaction semantics

The source specification makes `LIKE` the mandatory base reaction and delegates any extended
set to future administrator configuration. Neither the source specification nor UI Kit defines
additional concrete types. Stage 3 therefore permits only `LIKE`. The database uniqueness key
is `(publication, user, reaction_type)`; with one allowed type this also guarantees at most one
reaction by a user on a publication. `PUT` and `DELETE` are idempotent.

## Comment policy

Comments are flat in Stage 3. Only the author may edit or soft-delete an active comment. Other
employees receive no mutation controls and the server denies their mutation. Deleted text is
erased and never serialized. Unsafe control characters are removed while LF line breaks and tabs
are preserved. Mentions, threads, attachments, moderation and comment reactions are deferred.

## Authorization and realtime

`Publication.objects.visible_to(user)` is the only publication visibility source. The canonical
`visible_publication_or_404` boundary is used before every comment, reaction, ticket and socket
operation; invisible, draft and unknown publications are indistinguishable as 404.

Portal authentication is used only to mint a cryptographically random, 30-second ticket. Only a
SHA-256 ticket hash is stored in Redis DB 1. Consumption is atomic and one-time, and claims are
bound to a server-derived user and one publication. Origin is allow-listed. A connection joins
one safe publication group, accepts only `ping`, and expires after 15 minutes.

Events are schema version 1 and are queued only with `transaction.on_commit()`. Clients treat an
event as an invalidation hint and always re-fetch REST state.
