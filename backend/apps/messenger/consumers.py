import asyncio
import logging
import secrets
import time
import uuid
from collections import deque
from typing import cast

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from apps.identity.models import User
from apps.realtime.claims import RealtimeTicket
from apps.realtime.groups import conversation_group, session_control_group, user_control_group
from apps.realtime.session_security import ticket_session_deadline
from apps.realtime.socket_leases import (
    active_socket_count,
    release_socket,
    remove_presence,
    reserve_socket,
    set_typing,
    touch_presence,
)

from .models import ConversationMembership

logger = logging.getLogger(__name__)


class MessengerConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        if self.scope.get("ticket_error") or not self.scope.get("user"):
            logger.warning("messenger.websocket.authentication_failed")
            await self.close(code=4403)
            return
        scope = cast(dict[str, object], self.scope)
        user = cast(User, scope["user"])
        self.user_id = user.pk
        self.connection_id = secrets.token_urlsafe(16)
        self.lease_reserved = False
        self.conversation_groups: set[str] = set()
        try:
            allowed = await sync_to_async(reserve_socket, thread_sensitive=False)(
                user.pk, self.connection_id
            )
        except Exception:
            logger.exception("messenger.websocket.lease_failed", extra={"user_id": user.pk})
            await self.close(code=1013)
            return
        if not allowed:
            logger.warning("messenger.websocket.rate_limited", extra={"user_id": user.pk})
            await self.close(code=4429)
            return
        self.lease_reserved = True
        self.client_frame_times: deque[float] = deque()
        self.control_group_name = user_control_group(user.pk)
        self.session_group_name = session_control_group(cast(str, scope["session_fingerprint"]))
        self.conversation_groups = {
            conversation_group(conversation_id)
            for conversation_id in await self._conversation_ids(user.pk)
        }
        await self.channel_layer.group_add(self.control_group_name, self.channel_name)
        await self.channel_layer.group_add(self.session_group_name, self.channel_name)
        for group in self.conversation_groups:
            await self.channel_layer.group_add(group, self.channel_name)
        await self.accept()
        await sync_to_async(touch_presence, thread_sensitive=False)(
            self.user_id, self.connection_id
        )
        await self._broadcast_presence(True)
        logger.info(
            "messenger.websocket.connected",
            extra={"user_id": user.pk, "connection_id": self.connection_id},
        )
        self.lifetime_task = asyncio.create_task(self._expire())
        self.session_task = asyncio.create_task(self._watch_session())
        self.presence_task = asyncio.create_task(self._presence_heartbeat())

    @database_sync_to_async
    def _conversation_ids(self, user_id: int):
        return list(
            ConversationMembership.objects.filter(
                user_id=user_id, left_at__isnull=True
            ).values_list("conversation_id", flat=True)
        )

    @database_sync_to_async
    def _is_active_member(self, conversation_id: uuid.UUID) -> bool:
        return ConversationMembership.objects.filter(
            conversation_id=conversation_id,
            user_id=self.user_id,
            left_at__isnull=True,
        ).exists()

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

    async def _broadcast_presence(self, online: bool):
        event = {
            "type": "messenger.presence.changed",
            "user_id": self.user_id,
            "online": online,
        }
        for group in self.conversation_groups:
            await self.channel_layer.group_send(
                group,
                {"type": "messenger.presence.changed", "event": event},
            )

    async def _presence_heartbeat(self):
        while True:
            await asyncio.sleep(30)
            await sync_to_async(touch_presence, thread_sensitive=False)(
                self.user_id, self.connection_id
            )
            await self._broadcast_presence(True)

    async def _expire(self):
        await asyncio.sleep(settings.REALTIME_SOCKET_LIFETIME_SECONDS)
        await self.close(code=4000)

    async def disconnect(self, code):
        if hasattr(self, "control_group_name"):
            await self.channel_layer.group_discard(self.control_group_name, self.channel_name)
        if hasattr(self, "session_group_name"):
            await self.channel_layer.group_discard(self.session_group_name, self.channel_name)
        for group in getattr(self, "conversation_groups", set()):
            await self.channel_layer.group_discard(group, self.channel_name)
        if hasattr(self, "lifetime_task"):
            self.lifetime_task.cancel()
        if hasattr(self, "session_task"):
            self.session_task.cancel()
        if hasattr(self, "presence_task"):
            self.presence_task.cancel()
        if getattr(self, "lease_reserved", False):
            try:
                await sync_to_async(remove_presence, thread_sensitive=False)(
                    self.user_id, self.connection_id
                )
                await sync_to_async(release_socket, thread_sensitive=False)(
                    self.user_id, self.connection_id
                )
            except Exception:
                logger.exception(
                    "messenger.websocket.lease_release_failed",
                    extra={"user_id": self.user_id},
                )
            if await sync_to_async(active_socket_count, thread_sensitive=False)(self.user_id) == 0:
                await self._broadcast_presence(False)
            logger.info(
                "messenger.websocket.disconnected",
                extra={
                    "user_id": self.user_id,
                    "connection_id": self.connection_id,
                    "close_code": code,
                },
            )

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        now = time.monotonic()
        while self.client_frame_times and self.client_frame_times[0] <= now - 1:
            self.client_frame_times.popleft()
        if len(self.client_frame_times) >= settings.REALTIME_MAX_CLIENT_FRAMES_PER_SECOND:
            logger.warning("messenger.websocket.rate_limited", extra={"user_id": self.user_id})
            await self.close(code=4429)
            return
        self.client_frame_times.append(now)
        if bytes_data is not None or text_data is None or len(text_data) > 512:
            logger.warning(
                "messenger.websocket.protocol_violation",
                extra={"user_id": getattr(self, "user_id", None)},
            )
            await self.close(code=4400)
            return
        try:
            await super().receive(text_data=text_data, **kwargs)
        except (TypeError, ValueError):
            await self.close(code=4400)

    async def receive_json(self, content, **kwargs):
        if content == {"type": "ping"}:
            await self.send_json({"type": "pong"})
        elif (
            isinstance(content, dict)
            and content.get("type") == "typing"
            and isinstance(content.get("conversation_id"), str)
            and isinstance(content.get("is_typing"), bool)
        ):
            try:
                conversation_id = uuid.UUID(content["conversation_id"])
            except ValueError:
                await self.close(code=4400)
                return
            now = time.monotonic()
            if now - getattr(self, "last_typing_at", 0.0) < 0.5:
                return
            group = conversation_group(conversation_id)
            if group not in self.conversation_groups or not await self._is_active_member(
                conversation_id
            ):
                await self.close(code=4403)
                return
            self.last_typing_at = now
            await sync_to_async(set_typing, thread_sensitive=False)(
                self.user_id,
                str(conversation_id),
                self.connection_id,
                content["is_typing"],
            )
            await self.channel_layer.group_send(
                group,
                {
                    "type": (
                        "messenger.typing.started"
                        if content["is_typing"]
                        else "messenger.typing.stopped"
                    ),
                    "event": {
                        "type": (
                            "messenger.typing.started"
                            if content["is_typing"]
                            else "messenger.typing.stopped"
                        ),
                        "conversation_id": str(conversation_id),
                        "user_id": self.user_id,
                        "is_typing": content["is_typing"],
                    },
                },
            )
        else:
            logger.warning(
                "messenger.websocket.protocol_violation",
                extra={"user_id": getattr(self, "user_id", None)},
            )
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

    async def messenger_event(self, event):
        await self.send_json(event["event"])

    messenger_delivered_changed = messenger_event
    messenger_membership_role_changed = messenger_event
    messenger_message_edited = messenger_event
    messenger_message_deleted = messenger_event
    messenger_message_pinned = messenger_event
    messenger_message_unpinned = messenger_event
    messenger_reaction_changed = messenger_event
    messenger_conversation_updated = messenger_event
    messenger_typing_started = messenger_event
    messenger_typing_stopped = messenger_event
    messenger_presence_changed = messenger_event

    async def auth_invalidate(self, event):
        await self.close(code=4403)
