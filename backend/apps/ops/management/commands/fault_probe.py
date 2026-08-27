import json
import os
import time
import uuid
from typing import Any, cast
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.utils import timezone
from rest_framework.test import APIClient
from websockets.sync.client import connect

from apps.identity.models import User
from apps.messenger.models import Conversation, ConversationMembership, Message
from apps.messenger.services import send_message
from apps.notifications.models import Notification, NotificationFanoutEvent
from apps.publications.tasks import RECONCILIATION_HEARTBEAT_KEY
from apps.realtime.claims import RealtimeScope
from apps.realtime.models import RealtimeOutboxEvent
from apps.realtime.tickets import create_ticket

NAMESPACE = uuid.UUID("5063444c-2f8d-4dd9-91e4-5cbb55c00e9c")


class Command(BaseCommand):
    help = "Create and verify committed probes used by the isolated Stage 10 fault matrix."

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="action", required=True)
        create = subparsers.add_parser("create")
        create.add_argument("label")
        verify = subparsers.add_parser("verify")
        verify.add_argument("message_id", type=uuid.UUID)
        verify.add_argument("--timeout", type=int, default=90)
        heartbeat = subparsers.add_parser("heartbeat-stale")
        heartbeat.add_argument("--minimum-age", type=float, default=60)
        subparsers.add_parser("session-create")
        session_verify = subparsers.add_parser("session-verify")
        session_verify.add_argument("session_key")

    def handle(self, *args, **options):
        action = options["action"]
        if (
            action != "heartbeat-stale"
            and os.environ.get("TANDEM_ENVIRONMENT_PURPOSE") != "stage10-load"
        ):
            raise CommandError("Fault probes require TANDEM_ENVIRONMENT_PURPOSE=stage10-load")
        if action == "create":
            self._create(options["label"])
        elif action == "verify":
            self._verify(options["message_id"], options["timeout"])
        elif action == "heartbeat-stale":
            self._heartbeat_stale(options["minimum_age"])
        elif action == "session-create":
            self._session_create()
        else:
            self._session_verify(options["session_key"])

    @staticmethod
    def _load_user() -> User:
        user = User.objects.filter(username="load-0001", is_active=True).first()
        if user is None:
            raise CommandError("The isolated fault environment has no load-0001 fixture")
        return user

    def _create(self, label: str) -> None:
        author = self._load_user()
        membership = (
            ConversationMembership.objects.filter(user=author, left_at__isnull=True)
            .exclude(conversation__type=Conversation.Type.CHANNEL)
            .select_related("conversation")
            .first()
        )
        if membership is None:
            raise CommandError("The fault probe user has no writable conversation")
        client_message_id = uuid.uuid5(NAMESPACE, label)
        message, created = send_message(
            membership.conversation,
            author=author,
            client_message_id=client_message_id,
            body=f"Stage 10 fault probe {label}",
        )
        self.stdout.write(json.dumps({"message_id": str(message.pk), "created": created}))

    def _verify(self, message_id: uuid.UUID, timeout: int) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            fanout_pending = NotificationFanoutEvent.objects.filter(
                source_id=message_id,
                processed_at__isnull=True,
            ).exists()
            realtime_pending = RealtimeOutboxEvent.objects.filter(
                payload__message_id=str(message_id),
                delivered_at__isnull=True,
            ).exists()
            if not fanout_pending and not realtime_pending:
                break
            time.sleep(1)
        if Message.objects.filter(pk=message_id).count() != 1:
            raise CommandError("Committed fault-probe message was lost or duplicated")
        events = NotificationFanoutEvent.objects.filter(source_id=message_id)
        if events.count() != 1 or events.filter(processed_at__isnull=True).exists():
            raise CommandError("Notification fanout did not recover exactly once")
        duplicate_recipient = (
            Notification.objects.filter(
                source_id=message_id,
                notification_type=Notification.Type.NEW_MESSAGE,
            )
            .values("recipient_id")
            .annotate(rows=Count("pk"))
            .filter(rows__gt=1)
            .exists()
        )
        if duplicate_recipient:
            raise CommandError("Fault recovery duplicated a notification")
        if RealtimeOutboxEvent.objects.filter(
            payload__message_id=str(message_id), delivered_at__isnull=True
        ).exists():
            raise CommandError("Realtime outbox did not recover")

        client = APIClient()
        client.force_authenticate(user=User.objects.get(username="load-0001"))
        host = next((item for item in settings.ALLOWED_HOSTS if item != "127.0.0.1"), "127.0.0.1")
        meta = {"HTTP_HOST": host, "HTTP_X_FORWARDED_PROTO": "https"}
        for path in ("/api/v1/news", "/api/v1/search?q=производственная"):
            response = cast(Any, client).get(path, **meta)
            if response.status_code != 200:
                raise CommandError(
                    f"Recovered product probe failed for {path}: {response.status_code}"
                )
        self.stdout.write("Fault probe: PASS")

    def _heartbeat_stale(self, minimum_age: float) -> None:
        heartbeat = cache.get(RECONCILIATION_HEARTBEAT_KEY)
        if heartbeat and time.time() - float(heartbeat) < minimum_age:
            raise CommandError("Celery Beat heartbeat is not stale")
        self.stdout.write("Celery Beat stale-heartbeat detection: PASS")

    def _session_create(self) -> None:
        user = self._load_user()
        now = int(timezone.now().timestamp())
        session = SessionStore()
        session[SESSION_KEY] = str(user.pk)
        session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session["auth_started_at"] = now
        session["auth_last_seen_at"] = now
        session["security_epoch"] = user.security_epoch
        session.set_expiry(settings.SESSION_COOKIE_AGE)
        session.save()
        if not session.session_key:
            raise CommandError("Could not create the durable session probe")
        self.stdout.write(session.session_key)

    def _session_verify(self, session_key: str) -> None:
        user = self._load_user()
        client = APIClient()
        client.cookies[settings.SESSION_COOKIE_NAME] = session_key
        host = next((item for item in settings.ALLOWED_HOSTS if item != "127.0.0.1"), "127.0.0.1")
        meta = {"HTTP_HOST": host, "HTTP_X_FORWARDED_PROTO": "https"}
        response = cast(Any, client).get("/api/v1/auth/session", **meta)
        if response.status_code != 200 or not response.data.get("authenticated"):
            raise CommandError("Durable database session did not survive fault recovery")

        token, _ = create_ticket(
            user_id=user.pk,
            security_epoch=user.security_epoch,
            session_key=session_key,
            scope=RealtimeScope.MESSENGER,
        )
        origin = settings.REALTIME_ALLOWED_ORIGINS[0]
        uri = f"ws://127.0.0.1:8000/ws/v1/messenger?ticket={quote(token)}"
        try:
            with connect(uri, origin=origin, proxy=None, open_timeout=5, close_timeout=5) as socket:
                socket.send('{"type":"ping"}')
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    payload = json.loads(socket.recv(timeout=deadline - time.monotonic()))
                    if payload == {"type": "pong"}:
                        break
        except Exception as exc:
            raise CommandError("Realtime reconnect failed after fault recovery") from exc
        if payload != {"type": "pong"}:
            raise CommandError("Realtime reconnect returned an invalid payload")
        self.stdout.write("Durable session and realtime reconnect: PASS")
