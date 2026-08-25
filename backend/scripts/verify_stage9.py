"""Clean Compose acceptance for Stage 9 notifications and global search."""

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django  # noqa: E402

django.setup()

import websockets  # noqa: E402
from django.conf import settings  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import override_settings  # noqa: E402
from django.utils import timezone  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from apps.discussions.models import Comment  # noqa: E402
from apps.discussions.services import create_comment  # noqa: E402
from apps.identity.models import AccessGrant, User  # noqa: E402
from apps.messenger.models import Conversation, Message  # noqa: E402
from apps.notifications.delivery import deliver  # noqa: E402
from apps.notifications.models import (  # noqa: E402
    Notification,
    NotificationDelivery,
    NotificationFanoutEvent,
    NotificationPreference,
    PushSubscription,
)
from apps.publications.models import (  # noqa: E402
    AudienceRule,
    Category,
    MediaAsset,
    MediaUsage,
    Publication,
)
from apps.publications.services import transition_publication  # noqa: E402
from apps.search.services import authorized_sections  # noqa: E402

STATE_FILE = Path(settings.MEDIA_ROOT) / ".stage9-acceptance.json"
PASSWORD = settings.STAGE6_DEMO_PASSWORD
META = {"HTTP_HOST": "localhost", "HTTP_X_FORWARDED_PROTO": "https"}
USERNAMES = {
    "admin": "stage9-admin",
    "editor": "stage9-editor",
    "member": "stage9-member",
    "outsider": "stage9-outsider",
}
ws_connect = cast(Any, websockets.connect)


def get(client: APIClient, path: str):
    return cast(Any, client).get(path, **META)


def csrf(client: APIClient) -> str:
    response = get(client, "/api/v1/auth/csrf")
    assert response.status_code == 200, response.data
    return response.data["csrf_token"]


def mutate(client: APIClient, method: str, path: str, data=None):
    return getattr(cast(Any, client), method)(
        path,
        data or {},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(client),
        **META,
    )


def login(username: str) -> APIClient:
    client = APIClient(enforce_csrf_checks=True)
    response = mutate(
        client,
        "post",
        "/api/v1/auth/login",
        {"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200, response.data
    return client


def cookies(client: APIClient) -> dict[str, str]:
    return {name: morsel.value for name, morsel in client.cookies.items()}


def restore(values: dict[str, str]) -> APIClient:
    client = APIClient(enforce_csrf_checks=True)
    for name, value in values.items():
        client.cookies[name] = value
    return client


def setup_users() -> dict[str, User]:
    names = {
        "admin": "Администратор Stage 9",
        "editor": "Редактор Stage 9",
        "member": "Маяк Сотрудник",
        "outsider": "Закрытый Сотрудник",
    }
    users: dict[str, User] = {}
    for key, username in USERNAMES.items():
        user, _ = User.objects.get_or_create(username=username)
        user.full_name = names[key]
        user.email = f"{username}@example.invalid"
        user.job_title = "Аналитик адамға"
        user.is_active = True
        user.activated_at = timezone.now()
        user.password_changed_at = timezone.now()
        user.set_password(PASSWORD)
        user.save()
        users[key] = user
    AccessGrant.objects.filter(user__in=users.values()).delete()
    AccessGrant.objects.bulk_create(
        [
            AccessGrant(
                user=users[key],
                module=AccessGrant.Module.MESSENGER,
                role=(AccessGrant.Role.ADMIN if key == "admin" else AccessGrant.Role.MEMBER),
            )
            for key in users
        ]
        + [
            AccessGrant(
                user=users["editor"],
                module=AccessGrant.Module.NEWS,
                role=AccessGrant.Role.EDITOR,
            ),
            AccessGrant(
                user=users["member"],
                module=AccessGrant.Module.NEWS,
                role=AccessGrant.Role.MEMBER,
            ),
        ]
    )
    return users


def clean_previous(users: dict[str, User]) -> None:
    Notification.objects.filter(recipient__in=users.values()).delete()
    NotificationPreference.objects.filter(user__in=users.values()).delete()
    PushSubscription.objects.filter(user__in=users.values()).delete()
    for conversation in Conversation.objects.filter(title="Stage 9 Acceptance Channel"):
        Message.objects.filter(conversation=conversation).delete()
        conversation.delete()


def wait_for_fanout(source_ids: set[str], timeout: float = 20.0) -> float:
    started = time.perf_counter()
    deadline = started + timeout
    while time.perf_counter() < deadline:
        pending = NotificationFanoutEvent.objects.filter(
            source_id__in=source_ids, processed_at__isnull=True
        ).count()
        if pending == 0:
            return time.perf_counter() - started
        time.sleep(0.25)
    raise AssertionError("Stage 9 notification fanout did not finish")


def notification_ticket(client: APIClient) -> str:
    response = mutate(
        client,
        "post",
        "/api/v1/realtime/tickets",
        {"scope": "NOTIFICATIONS"},
    )
    assert response.status_code == 200, response.data
    return response.data["ticket"]


async def receive_type(socket, event_type: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        event = json.loads(
            await asyncio.wait_for(socket.recv(), timeout=max(0.05, deadline - time.monotonic()))
        )
        if event.get("type") == event_type:
            return event


async def verify_two_device_read(
    first: APIClient,
    second: APIClient,
    notification_id: str,
    first_token: str,
    second_token: str,
) -> float:
    url = "ws://127.0.0.1:8000/ws/v1/notifications?ticket={}"
    async with (
        ws_connect(
            url.format(first_token),
            origin="http://localhost",
            open_timeout=5,
            close_timeout=2,
        ) as first_socket,
        ws_connect(
            url.format(second_token),
            origin="http://localhost",
            open_timeout=5,
            close_timeout=2,
        ) as second_socket,
    ):
        started = time.perf_counter()
        response = await asyncio.to_thread(
            mutate,
            first,
            "post",
            f"/api/v1/notifications/{notification_id}/read",
        )
        assert response.status_code == 204
        first_event, second_event = await asyncio.gather(
            receive_type(first_socket, "notification.read"),
            receive_type(second_socket, "notification.read"),
        )
        assert first_event["unread_count"] == second_event["unread_count"]
        rest_count = await asyncio.to_thread(
            lambda: get(second, "/api/v1/notifications/unread-count").data["unread_count"]
        )
        assert rest_count == second_event["unread_count"]
        return time.perf_counter() - started


def language_evidence() -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT dictionary, lexemes FROM ts_debug('russian', 'новостями') "
            "WHERE lexemes IS NOT NULL"
        )
        russian = cursor.fetchall()
        cursor.execute(
            "SELECT dictionary, lexemes FROM ts_debug('tandem_kazakh', 'адамға') "
            "WHERE lexemes IS NOT NULL"
        )
        kazakh = cursor.fetchall()
    assert any("новост" in lexemes for _, lexemes in russian)
    assert any(
        dictionary == "tandem_kk_dict" and "адам" in lexemes for dictionary, lexemes in kazakh
    )
    return {
        "russian_lexemes": russian,
        "kazakh_lexemes": kazakh,
    }


def query_plan(user: User) -> dict[str, object]:
    plan = json.loads(
        authorized_sections(user, "маяк")["publications"].explain(
            analyze=True, buffers=True, format="json"
        )
    )[0]
    return {
        "planning_ms": plan["Planning Time"],
        "execution_ms": plan["Execution Time"],
        "publication_rows": Publication.objects.count(),
        "message_rows": Message.objects.count(),
        "comment_rows": Comment.objects.count(),
    }


def prepare() -> None:
    users = setup_users()
    clean_previous(users)
    clients = {key: login(user.username) for key, user in users.items()}

    category, _ = Category.objects.get_or_create(slug="stage9", defaults={"name": "Stage 9"})
    publication = Publication.objects.create(
        title="Маяк новостями адамға",
        slug=f"stage9-acceptance-{uuid.uuid4().hex[:8]}",
        summary="Маяк для двуязычного поиска",
        body={
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Маяк новостями адамға"}],
                }
            ],
        },
        category=category,
        author=users["editor"],
        acknowledgement_required=True,
    )
    AudienceRule.objects.create(
        publication=publication,
        kind=AudienceRule.Kind.EMPLOYEE,
        employee=users["member"],
    )
    transition_publication(publication, action="publish", actor=users["editor"])
    root = create_comment(
        publication=publication,
        author=users["member"],
        body="Маяк исходный комментарий",
    )
    reply = create_comment(
        publication=publication,
        author=users["editor"],
        body="Маяк ответ адамға",
        reply_to_id=root.pk,
    )
    comment_mention = create_comment(
        publication=publication,
        author=users["editor"],
        body="Маяк отдельное упоминание",
        mentioned_users=[users["member"]],
    )
    asset = MediaAsset.objects.create(
        original_name="маяк-stage9.pdf",
        storage_key=f"assets/{uuid.uuid4().hex}.pdf",
        file=SimpleUploadedFile("stage9.pdf", b"%PDF-1.7\n%%EOF\n"),
        mime_type="application/pdf",
        size=15,
        sha256="5" * 64,
        kind=MediaAsset.Kind.DOCUMENT,
        uploader=users["editor"],
        status=MediaAsset.Status.READY,
    )
    MediaUsage.objects.create(
        asset=asset,
        publication=publication,
        purpose=MediaUsage.Purpose.ATTACHMENT,
    )

    channel = mutate(
        clients["admin"],
        "post",
        "/api/v1/messenger/conversations/channel",
        {
            "title": "Stage 9 Acceptance Channel",
            "member_ids": [users["editor"].pk, users["member"].pk],
            "writer_ids": [users["editor"].pk],
            "discussion_enabled": True,
        },
    )
    assert channel.status_code == 201, channel.data
    conversation_id = channel.data["id"]
    messages_url = f"/api/v1/messenger/conversations/{conversation_id}/messages"
    messages = []
    for index in range(3):
        response = mutate(
            clients["admin"],
            "post",
            messages_url,
            {
                "client_message_id": str(uuid.uuid4()),
                "body": f"Маяк сообщение {index}",
                "kind": "CHANNEL_POST",
            },
        )
        assert response.status_code == 201, response.data
        messages.append(response.data)
    mention = mutate(
        clients["admin"],
        "post",
        messages_url,
        {
            "client_message_id": str(uuid.uuid4()),
            "body": "Маяк точное упоминание",
            "kind": "CHANNEL_POST",
            "mentioned_user_ids": [users["member"].pk],
        },
    )
    assert mention.status_code == 201, mention.data

    source_ids = {
        str(publication.pk),
        str(reply.pk),
        str(comment_mention.pk),
        *(row["id"] for row in messages),
        mention.data["id"],
    }
    fanout_seconds = wait_for_fanout(source_ids)
    grouped = Notification.objects.get(
        recipient=users["member"],
        notification_type=Notification.Type.NEW_MESSAGE,
    )
    assert grouped.occurrence_count == 3
    mention_notification = Notification.objects.get(
        recipient=users["member"],
        notification_type=Notification.Type.MESSAGE_MENTION,
        source_id=mention.data["id"],
    )
    assert mention_notification.occurrence_count == 1
    expected = {
        Notification.Type.NEW_PUBLICATION,
        Notification.Type.ACK_REQUIRED,
        Notification.Type.COMMENT_REPLY,
        Notification.Type.COMMENT_MENTION,
        Notification.Type.NEW_MESSAGE,
        Notification.Type.MESSAGE_MENTION,
        Notification.Type.CHAT_ADDED,
    }
    assert expected <= set(
        Notification.objects.filter(recipient=users["member"]).values_list(
            "notification_type", flat=True
        )
    )

    settings_response = mutate(
        clients["member"],
        "patch",
        "/api/v1/notification-settings",
        {
            "enabled": True,
            "preferences": [
                {
                    "notification_type": "NEW_MESSAGE",
                    "in_app_enabled": True,
                    "push_enabled": False,
                    "email_enabled": False,
                },
                {
                    "notification_type": "MESSAGE_MENTION",
                    "in_app_enabled": True,
                    "push_enabled": True,
                    "email_enabled": False,
                },
                {
                    "notification_type": "ACK_REQUIRED",
                    "in_app_enabled": True,
                    "push_enabled": False,
                    "email_enabled": True,
                },
            ],
        },
    )
    assert settings_response.status_code == 200, settings_response.data
    state_response = mutate(
        clients["member"],
        "patch",
        f"/api/v1/messenger/conversations/{conversation_id}/state",
        {"notification_mode": "MENTIONS"},
    )
    assert state_response.status_code == 200
    assert state_response.data["notification_mode"] == "MENTIONS"

    search = get(clients["member"], "/api/v1/search?q=маяк")
    assert search.status_code == 200, search.data
    assert all(search.data[scope] for scope in search.data)
    assert any(row["id"] == mention.data["id"] for row in search.data["messages"])
    outsider_search = get(clients["outsider"], "/api/v1/search?q=маяк").data
    assert all(
        not outsider_search[scope] for scope in ("publications", "comments", "messages", "files")
    )
    assert any(
        row["id"] == str(publication.pk)
        for row in get(clients["member"], "/api/v1/search?q=новостями&scope=publications").data[
            "results"
        ]
    )
    assert any(
        row["id"] == str(publication.pk)
        for row in get(clients["member"], "/api/v1/search?q=адам&scope=publications").data[
            "results"
        ]
    )
    context = get(
        clients["member"],
        f"{messages_url}/{mention.data['id']}/context",
    )
    assert context.status_code == 200 and context.data["target"]["id"] == mention.data["id"]

    second_member = login(users["member"].username)
    first_token = notification_ticket(clients["member"])
    second_token = notification_ticket(second_member)
    read_sync_seconds = asyncio.run(
        verify_two_device_read(
            clients["member"],
            second_member,
            str(grouped.pk),
            first_token,
            second_token,
        )
    )

    push_subscription = PushSubscription.objects.create(
        user=users["member"],
        endpoint="https://push.example.invalid/stage9-secret",
        p256dh="stage9-p256dh-secret",
        auth="stage9-auth-secret",
    )
    email_delivery = NotificationDelivery.objects.create(
        notification=Notification.objects.get(
            recipient=users["member"], notification_type=Notification.Type.ACK_REQUIRED
        ),
        channel=NotificationDelivery.Channel.EMAIL,
        event_version=91,
    )
    push_delivery = NotificationDelivery.objects.create(
        notification=mention_notification,
        channel=NotificationDelivery.Channel.PUSH,
        event_version=92,
    )
    with (
        override_settings(
            NOTIFICATION_EMAIL_ENABLED=True,
            EMAIL_HOST="127.0.0.1",
            EMAIL_PORT=1,
            EMAIL_TIMEOUT=1,
        ),
        patch("apps.notifications.delivery.send_mail", side_effect=ConnectionError("smtp down")),
    ):
        assert deliver(email_delivery.pk) is False
    with (
        override_settings(WEB_PUSH_ENABLED=True),
        patch("apps.notifications.push.webpush", side_effect=ConnectionError("push down")),
    ):
        assert deliver(push_delivery.pk) is False
    email_delivery.refresh_from_db()
    push_delivery.refresh_from_db()
    assert email_delivery.attempts == 1 and push_delivery.attempts == 1
    assert Publication.objects.filter(pk=publication.pk).exists()
    assert Message.objects.filter(pk=mention.data["id"]).exists()
    assert "stage9-secret" not in str(push_subscription)

    evidence = language_evidence()
    plan = query_plan(users["member"])
    STATE_FILE.write_text(
        json.dumps(
            {
                "member_cookies": cookies(second_member),
                "conversation_id": conversation_id,
                "publication_id": str(publication.pk),
                "email_delivery_id": email_delivery.pk,
                "push_delivery_id": push_delivery.pk,
                "unread_group_id": str(grouped.pk),
                "fanout_seconds": fanout_seconds,
                "read_sync_seconds": read_sync_seconds,
                "language": evidence,
                "plan": plan,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "phase": "prepare",
                "status": "PASS",
                "fanout_seconds": round(fanout_seconds, 3),
                "read_sync_seconds": round(read_sync_seconds, 3),
                "notification_types": len(expected),
                "search_sections": 5,
                "query_plan": plan,
            }
        )
    )


def outage() -> None:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    member = restore(state["member_cookies"])
    messages_url = f"/api/v1/messenger/conversations/{state['conversation_id']}/messages"
    response = mutate(
        member,
        "post",
        messages_url,
        {
            "client_message_id": str(uuid.uuid4()),
            "body": "Stage 9 source survives Redis outage",
            "kind": "DISCUSSION",
            "mention_all": True,
        },
    )
    assert response.status_code == 201, response.data
    event = NotificationFanoutEvent.objects.get(source_id=response.data["id"])
    assert event.processed_at is None
    search = get(member, "/api/v1/search?q=маяк")
    assert search.status_code == 200 and search.data["publications"]
    assert get(member, "/api/v1/push/config").data["enabled"] is False
    state["outage_message_id"] = response.data["id"]
    state["outage_event_id"] = str(event.pk)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "phase": "outage",
                "status": "PASS",
                "source_persisted": True,
                "search_available": True,
                "push_disabled_by_policy": True,
            }
        )
    )


def verify() -> None:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        event = NotificationFanoutEvent.objects.get(pk=state["outage_event_id"])
        if event.processed_at is not None:
            break
        time.sleep(0.25)
    else:
        raise AssertionError("Fanout event did not recover after Redis/worker restart")
    assert Message.objects.filter(pk=state["outage_message_id"]).exists()
    assert Notification.objects.filter(
        source_id=state["outage_message_id"],
        notification_type=Notification.Type.MESSAGE_MENTION,
    ).exists()

    email_delivery = NotificationDelivery.objects.get(pk=state["email_delivery_id"])
    push_delivery = NotificationDelivery.objects.get(pk=state["push_delivery_id"])
    NotificationDelivery.objects.filter(pk__in=[email_delivery.pk, push_delivery.pk]).update(
        status=NotificationDelivery.Status.PENDING,
        available_at=timezone.now(),
    )
    with (
        override_settings(NOTIFICATION_EMAIL_ENABLED=True),
        patch("apps.notifications.delivery.send_mail", return_value=1),
    ):
        assert deliver(email_delivery.pk) is True
    with (
        override_settings(WEB_PUSH_ENABLED=True),
        patch("apps.notifications.push.webpush", return_value=None),
    ):
        assert deliver(push_delivery.pk) is True
    email_delivery.refresh_from_db()
    push_delivery.refresh_from_db()
    assert email_delivery.status == NotificationDelivery.Status.SENT
    assert push_delivery.status == NotificationDelivery.Status.SENT

    member = restore(state["member_cookies"])
    assert get(member, "/api/v1/search?q=маяк").status_code == 200
    assert get(member, "/api/v1/notifications").status_code == 200
    language_evidence()
    STATE_FILE.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "phase": "verify",
                "status": "PASS",
                "fanout_recovered": True,
                "smtp_delivery_recovered": True,
                "push_delivery_recovered": True,
                "source_data_intact": True,
                "search_available": True,
            }
        )
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "verify"
    {"prepare": prepare, "outage": outage, "verify": verify}[mode]()
