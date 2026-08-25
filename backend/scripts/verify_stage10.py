"""Operational acceptance checks for Stage 10 on a running production deployment."""

import http.client
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, cast

if not __debug__:
    raise SystemExit("Stage 10 verification must run without Python optimization (-O)")

PRODUCTION_SETTINGS = "config.settings.production"
if os.getenv("DJANGO_SETTINGS_MODULE") != PRODUCTION_SETTINGS:
    raise SystemExit("Stage 10 verification requires config.settings.production")
os.environ.pop("PYTHONOPTIMIZE", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def configured_host() -> str:
    for host in settings.ALLOWED_HOSTS:
        candidate = host.removeprefix(".")
        if candidate not in {"*", "localhost", "127.0.0.1"}:
            return candidate
    raise RuntimeError("No production host is configured in ALLOWED_HOSTS")


HTTP_HOST = configured_host()
META = {"HTTP_HOST": HTTP_HOST, "HTTP_X_FORWARDED_PROTO": "https"}


def response_data(response) -> Any:
    return cast(Any, response).data


def deployed_json(path: str) -> tuple[int, dict[str, Any]]:
    connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
    try:
        connection.request(
            "GET",
            path,
            headers={"Host": HTTP_HOST, "X-Forwarded-Proto": "https"},
        )
        response = connection.getresponse()
        body = response.read(1_048_576)
    finally:
        connection.close()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} returned invalid JSON") from exc
    require(isinstance(payload, dict), f"{path} did not return a JSON object")
    return response.status, payload


def verify_database() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        require(cursor.fetchone() == (1,), "PostgreSQL SELECT 1 failed")


def verify_media() -> None:
    call_command("verify_media_integrity")
    ready = MediaAsset.objects.filter(status=MediaAsset.Status.READY)
    require(ready.exists(), "Stage 10 requires at least one READY media fixture")


def verify_runtime_config() -> None:
    status, payload = deployed_json("/api/v1/runtime/meta")
    require(status == 200, f"Runtime metadata returned HTTP {status}: {payload}")
    require(payload.get("version") == settings.APP_VERSION, "Runtime version does not match")
    require(payload.get("revision") == settings.APP_GIT_SHA, "Runtime revision does not match")

    status, payload = deployed_json("/api/v1/health/ready")
    require(status == 200, f"Readiness returned HTTP {status}: {payload}")
    require("credentials" not in str(payload).casefold(), "Readiness exposed credentials")


def verify_background_jobs() -> None:
    heartbeat = cache.get(RECONCILIATION_HEARTBEAT_KEY)
    require(bool(heartbeat), "Celery reconciliation heartbeat is missing")
    age = max(0.0, time.time() - float(heartbeat))
    require(age < 60, f"Celery reconciliation heartbeat is stale ({age:.1f}s)")


def verify_backlogs() -> None:
    require(
        not RealtimeOutboxEvent.objects.filter(delivered_at__isnull=True).exists(),
        "Realtime outbox has undelivered events",
    )
    require(
        not NotificationFanoutEvent.objects.filter(processed_at__isnull=True).exists(),
        "Notification fanout has unprocessed events",
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
    if platform_admin is None:
        raise RuntimeError("No active platform administrator fixture")
    joined = ConversationMembership.objects.filter(
        user=platform_admin, left_at__isnull=True
    ).values("conversation_id")
    private_conversation = (
        Conversation.objects.exclude(pk__in=joined)
        .filter(type__in=[Conversation.Type.DIRECT, Conversation.Type.GROUP])
        .first()
    )
    if private_conversation is None:
        raise RuntimeError("No private non-member conversation fixture")
    client = APIClient()
    cast(Any, client).force_authenticate(user=platform_admin)
    response = cast(Any, client).get(
        f"/api/v1/messenger/conversations/{private_conversation.pk}", **META
    )
    require(
        response.status_code == 404, f"Private conversation check failed: {response_data(response)}"
    )


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
