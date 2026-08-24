import re
from typing import cast
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware

from apps.publications.services import visible_publication_or_404

from .claims import RealtimeScope
from .security import valid_user_for_ticket
from .tickets import consume_ticket


class TicketAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        mutable_scope = cast(dict[str, object], scope)
        token = parse_qs(scope.get("query_string", b"").decode("ascii", "ignore")).get(
            "ticket", [""]
        )[0]
        claims = await sync_to_async(consume_ticket, thread_sensitive=False)(token)
        path = scope.get("path", "")
        publication_match = re.fullmatch(r"/ws/v1/publications/([0-9a-fA-F-]{36})", path)
        if publication_match:
            expected_scope = RealtimeScope.NEWS_PUBLICATION
            resource_id = publication_match.group(1)
        elif path == "/ws/v1/messenger":
            expected_scope = RealtimeScope.MESSENGER
            resource_id = None
        else:
            claims = None
            expected_scope = None
            resource_id = None
        if claims is None or claims.scope != expected_scope or claims.resource_id != resource_id:
            mutable_scope["ticket_error"] = True
            return await super().__call__(scope, receive, send)
        user = await database_sync_to_async(valid_user_for_ticket)(claims)
        if user is None:
            mutable_scope["ticket_error"] = True
            return await super().__call__(scope, receive, send)
        if claims.scope == RealtimeScope.NEWS_PUBLICATION:
            try:
                await database_sync_to_async(visible_publication_or_404)(user, resource_id)
            except Exception:
                mutable_scope["ticket_error"] = True
                return await super().__call__(scope, receive, send)
        mutable_scope["user"] = user
        mutable_scope["realtime_scope"] = claims.scope
        mutable_scope["resource_id"] = resource_id
        mutable_scope["publication_id"] = resource_id
        return await super().__call__(scope, receive, send)
