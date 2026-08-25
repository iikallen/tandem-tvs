# Stage 9 security review scope

The release review covers notification ownership and cross-user reads, target reauthorization,
search authorization order, private membership intervals, protected media, deleted/hidden content,
subscription-secret and VAPID leakage, push CSRF/amplification, email content privacy, preference and
mute bypass, `@all` abuse, channel role/policy bypass, fanout duplication/races, WebSocket spoofing
and snippet XSS.

Security invariants:

- every notification query is recipient-scoped and every target is independently authorized;
- every search queryset applies object visibility before FTS, rank, headline or count operations;
- snippets are plain strings and the frontend never renders them with `dangerouslySetInnerHTML`;
- deleted messages, deleted/hidden comments and unattached/protected files cannot enter results;
- realtime events are server-originated hints without private content;
- source transactions contain only a durable fanout event, never push or SMTP I/O;
- channel writes and mention expansion use current active membership, not client claims;
- preferences and temporary mutes are enforced during backend fanout.

