import asyncio
from typing import cast

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from apps.identity.models import User
from apps.realtime.groups import conversation_group, user_control_group

from .models import ConversationMembership


class MessengerConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        if self.scope.get("ticket_error") or not self.scope.get("user"):
            await self.close(code=4403)
            return
        scope = cast(dict[str, object], self.scope)
        user = cast(User, scope["user"])
        self.control_group_name = user_control_group(user.pk)
        self.conversation_groups = {
            conversation_group(conversation_id)
            for conversation_id in await self._conversation_ids(user.pk)
        }
        await self.channel_layer.group_add(self.control_group_name, self.channel_name)
        for group in self.conversation_groups:
            await self.channel_layer.group_add(group, self.channel_name)
        await self.accept()
        self.lifetime_task = asyncio.create_task(self._expire())

    @database_sync_to_async
    def _conversation_ids(self, user_id: int):
        return list(
            ConversationMembership.objects.filter(user_id=user_id).values_list(
                "conversation_id", flat=True
            )
        )

    async def _expire(self):
        await asyncio.sleep(settings.REALTIME_SOCKET_LIFETIME_SECONDS)
        await self.close(code=4000)

    async def disconnect(self, code):
        if hasattr(self, "control_group_name"):
            await self.channel_layer.group_discard(self.control_group_name, self.channel_name)
        for group in getattr(self, "conversation_groups", set()):
            await self.channel_layer.group_discard(group, self.channel_name)
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

    async def messenger_conversation_created(self, event):
        group = conversation_group(event["event"]["conversation_id"])
        self.conversation_groups.add(group)
        await self.channel_layer.group_add(group, self.channel_name)
        await self.send_json(event["event"])

    async def messenger_membership_added(self, event):
        await self.messenger_conversation_created(event)

    async def messenger_membership_removed(self, event):
        group = conversation_group(event["event"]["conversation_id"])
        self.conversation_groups.discard(group)
        await self.channel_layer.group_discard(group, self.channel_name)
        await self.send_json(event["event"])

    async def messenger_message_created(self, event):
        await self.send_json(event["event"])

    async def messenger_read_changed(self, event):
        await self.send_json(event["event"])

    async def auth_invalidate(self, event):
        await self.close(code=4403)
