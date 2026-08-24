import asyncio
from typing import cast

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from apps.identity.models import User
from apps.realtime.groups import publication_group, user_control_group


class PublicationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        if self.scope.get("ticket_error") or not self.scope.get("user"):
            await self.close(code=4403)
            return
        scope = cast(dict[str, object], self.scope)
        user = cast(User, scope["user"])
        self.group_name = publication_group(scope["publication_id"])
        self.control_group_name = user_control_group(user.pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.channel_layer.group_add(self.control_group_name, self.channel_name)
        await self.accept()
        self.lifetime_task = asyncio.create_task(self._expire())

    async def _expire(self):
        await asyncio.sleep(settings.REALTIME_SOCKET_LIFETIME_SECONDS)
        await self.close(code=4000)

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if hasattr(self, "control_group_name"):
            await self.channel_layer.group_discard(self.control_group_name, self.channel_name)
        if hasattr(self, "lifetime_task"):
            self.lifetime_task.cancel()

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        if bytes_data is not None or text_data is None or len(text_data) > 512:
            await self.close(code=4400)
            return
        try:
            await super().receive(text_data=text_data, **kwargs)
        except (TypeError, ValueError):
            await self.close(code=4400)

    async def receive_json(self, content, **kwargs):
        if content == {"type": "ping"}:
            await self.send_json({"type": "pong"})
        else:
            await self.close(code=4400)

    async def publication_event(self, event):
        await self.send_json(event["event"])

    async def auth_invalidate(self, event):
        await self.close(code=4403)
