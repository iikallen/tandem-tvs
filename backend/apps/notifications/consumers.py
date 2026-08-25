import asyncio
import time
from collections import deque
from typing import cast

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from apps.identity.models import User
from apps.realtime.claims import RealtimeTicket
from apps.realtime.groups import notification_group, session_control_group, user_control_group
from apps.realtime.session_security import ticket_session_deadline


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        if self.scope.get("ticket_error") or not self.scope.get("user"):
            await self.close(code=4403)
            return
        scope = cast(dict[str, object], self.scope)
        user = cast(User, scope["user"])
        self.group_name = notification_group(user.pk)
        self.control_group_name = user_control_group(user.pk)
        self.session_group_name = session_control_group(cast(str, scope["session_fingerprint"]))
        self.client_frame_times: deque[float] = deque()
        for group in (self.group_name, self.control_group_name, self.session_group_name):
            await self.channel_layer.group_add(group, self.channel_name)
        await self.accept()
        self.lifetime_task = asyncio.create_task(self._expire())
        self.session_task = asyncio.create_task(self._watch_session())

    async def _watch_session(self):
        scope = cast(dict[str, object], self.scope)
        claims = cast(RealtimeTicket, scope["realtime_claims"])
        deadline = cast(int, scope["session_deadline"])
        while True:
            await asyncio.sleep(max(0, deadline - int(time.time())))
            refreshed = await database_sync_to_async(ticket_session_deadline)(claims)
            if refreshed is None or refreshed <= int(time.time()):
                await self.close(code=4403)
                return
            deadline = refreshed

    async def _expire(self):
        await asyncio.sleep(settings.REALTIME_SOCKET_LIFETIME_SECONDS)
        await self.close(code=4000)

    async def disconnect(self, code):
        for group in (
            getattr(self, "group_name", None),
            getattr(self, "control_group_name", None),
            getattr(self, "session_group_name", None),
        ):
            if group:
                await self.channel_layer.group_discard(group, self.channel_name)
        for task in (
            getattr(self, "lifetime_task", None),
            getattr(self, "session_task", None),
        ):
            if task:
                task.cancel()

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        now = time.monotonic()
        while self.client_frame_times and self.client_frame_times[0] <= now - 1:
            self.client_frame_times.popleft()
        if len(self.client_frame_times) >= settings.REALTIME_MAX_CLIENT_FRAMES_PER_SECOND:
            await self.close(code=4429)
            return
        self.client_frame_times.append(now)
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

    async def notification_changed(self, event):
        await self.send_json(event["event"])

    notification_read = notification_changed
    notification_read_all = notification_changed

    async def auth_invalidate(self, event):
        await self.close(code=4403)
