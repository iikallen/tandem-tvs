"""Operational acceptance checks for Stage 10 on a running Compose deployment."""

import os
import sys
import time
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.core.cache import cache  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from apps.identity.models import AccessGrant, User  # noqa: E402
from apps.messenger.models import Conversation, ConversationMembership  # noqa: E402
from apps.notifications.models import NotificationFanoutEvent  # noqa: E402
from apps.publications.models import MediaAsset  # noqa: E402
from apps.publications.tasks import RECONCILIATION_HEARTBEAT_KEY  # noqa: E402
from apps.realtime.models import RealtimeOutboxEvent  # noqa: E402

META = {"HTTP_HOST": "localhost", "HTTP_X_FORWARDED_PROTO": "https"}


def response_data(response) -> Any:
    return cast(Any, response).data


def verify_database() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)


def verify_media() -> None:
    call_command("verify_media_integrity")
    ready = MediaAsset.objects.filter(status=MediaAsset.Status.READY)
    assert ready.exists(), "Stage 10 requires at least one READY media fixture"


def verify_runtime_config() -> None:
    client = APIClient()
    response = cast(Any, client).get("/api/v1/runtime/meta", **META)
    assert response.status_code == 200, response_data(response)
    payload = response_data(response)
    assert payload["version"] == settings.APP_VERSION
    assert payload["revision"] == settings.APP_GIT_SHA

    ready = cast(Any, client).get("/api/v1/health/ready", **META)
    assert ready.status_code == 200, response_data(ready)
    assert "credentials" not in str(response_data(ready)).casefold()


def verify_background_jobs() -> None:
    heartbeat = cache.get(RECONCILIATION_HEARTBEAT_KEY)
    assert heartbeat, "Celery reconciliation heartbeat is missing"
    age = max(0.0, time.time() - float(heartbeat))
    assert age < 60, f"Celery reconciliation heartbeat is stale ({age:.1f}s)"


def verify_backlogs() -> None:
    assert not RealtimeOutboxEvent.objects.filter(delivered_at__isnull=True).exists(), (
        "Realtime outbox has undelivered events"
    )
    assert not NotificationFanoutEvent.objects.filter(processed_at__isnull=True).exists(), (
        "Notification fanout has unprocessed events"
    )


def verify_private_conversation_isolation() -> None:
    platform_admin = (
        User.objects.filter(
            access_grants__module=AccessGrant.Module.PLATFORM,
            access_grants__role=AccessGrant.Role.ADMIN,
            is_active=True,
        )
        .distinct()
        .first()
    )
    assert platform_admin, "No active platform administrator fixture"
    joined = ConversationMembership.objects.filter(
        user=platform_admin, left_at__isnull=True
    ).values("conversation_id")
    private_conversation = (
        Conversation.objects.exclude(pk__in=joined)
        .filter(type__in=[Conversation.Type.DIRECT, Conversation.Type.GROUP])
        .first()
    )
    assert private_conversation, "No private non-member conversation fixture"
    client = APIClient()
    cast(Any, client).force_authenticate(user=platform_admin)
    response = cast(Any, client).get(
        f"/api/v1/messenger/conversations/{private_conversation.pk}", **META
    )
    assert response.status_code == 404, response_data(response)


def main() -> None:
    verify_database()
    verify_media()
    verify_runtime_config()
    verify_background_jobs()
    verify_backlogs()
    verify_private_conversation_isolation()
    print("Stage 10: PASS")


if __name__ == "__main__":
    main()
