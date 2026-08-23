import re
from typing import cast
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.middleware import BaseMiddleware

from apps.identity.models import User
from apps.publications.services import visible_publication_or_404

from .tickets import consume_ticket


class TicketAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        mutable_scope = cast(dict[str, object], scope)
        params = parse_qs(scope.get("query_string", b"").decode("ascii", "ignore"))
        token = params.get("ticket", [""])[0]
        claims = await sync_to_async(consume_ticket, thread_sensitive=False)(token)
        match = re.fullmatch(r"/ws/v1/publications/([0-9a-fA-F-]{36})", scope.get("path", ""))
        route_publication_id = match.group(1) if match else ""
        if claims is None or claims.publication_id != route_publication_id:
            mutable_scope["ticket_error"] = True
            return await super().__call__(scope, receive, send)
        try:
            user = await User.objects.aget(pk=claims.user_id, is_active=True)
            await sync_to_async(visible_publication_or_404)(user, route_publication_id)
        except Exception:
            mutable_scope["ticket_error"] = True
            return await super().__call__(scope, receive, send)
        mutable_scope["user"] = user
        mutable_scope["publication_id"] = route_publication_id
        return await super().__call__(scope, receive, send)
