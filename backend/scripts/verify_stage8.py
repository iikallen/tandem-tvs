"""Clean Compose acceptance for Stage 8 Messenger Complete."""

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django  # noqa: E402

django.setup()

import websockets  # noqa: E402
from django.conf import settings  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.utils import timezone  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402
from websockets.exceptions import ConnectionClosed  # noqa: E402

from apps.identity.models import User  # noqa: E402
from apps.messenger.models import (  # noqa: E402
    Conversation,
    ConversationMembership,
    Message,
    PinnedMessage,
)
from apps.publications.models import AuditEvent  # noqa: E402
from apps.realtime.models import RealtimeOutboxEvent  # noqa: E402

STATE_FILE = Path(settings.MEDIA_ROOT) / ".stage8-acceptance.json"
PASSWORD = settings.STAGE6_DEMO_PASSWORD
META = {"HTTP_HOST": "localhost", "HTTP_X_FORWARDED_PROTO": "https"}
ACCEPTANCE_ORIGIN = os.getenv("ACCEPTANCE_ORIGIN", "http://localhost")
ws_connect = cast(Any, websockets.connect)


def csrf(client: APIClient) -> str:
    response = cast(Any, client).get("/api/v1/auth/csrf", **META)
    assert response.status_code == 200, response.data
    return response.data["csrf_token"]


def mutate(client: APIClient, method: str, path: str, data=None, *, multipart=False):
    return getattr(cast(Any, client), method)(
        path,
        data or {},
        format="multipart" if multipart else "json",
        HTTP_X_CSRFTOKEN=csrf(client),
        **META,
    )


def get(client: APIClient, path: str):
    return cast(Any, client).get(path, **META)


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
    return {key: morsel.value for key, morsel in client.cookies.items()}


def restore(values: dict[str, str]) -> APIClient:
    client = APIClient(enforce_csrf_checks=True)
    for key, value in values.items():
        client.cookies[key] = value
    return client


def ticket(client: APIClient) -> str:
    response = mutate(client, "post", "/api/v1/realtime/tickets", {"scope": "MESSENGER"})
    assert response.status_code == 200, response.data
    return response.data["ticket"]


def ws_url(token: str) -> str:
    return f"ws://127.0.0.1:8000/ws/v1/messenger?ticket={token}"


async def receive_type(socket, event_type: str, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        event = json.loads(
            await asyncio.wait_for(socket.recv(), timeout=max(0.01, deadline - time.monotonic()))
        )
        if event.get("type") == event_type:
            return event


async def assert_session_logout(first_token: str, second_token: str, first: APIClient) -> None:
    async with (
        ws_connect(
            ws_url(first_token), origin=ACCEPTANCE_ORIGIN, open_timeout=5, close_timeout=2
        ) as first_socket,
        ws_connect(
            ws_url(second_token), origin=ACCEPTANCE_ORIGIN, open_timeout=5, close_timeout=2
        ) as second_socket,
    ):
        response = await asyncio.to_thread(mutate, first, "post", "/api/v1/auth/logout")
        assert response.status_code == 204
        try:
            while True:
                await asyncio.wait_for(first_socket.recv(), timeout=2)
        except ConnectionClosed as exc:
            assert exc.code == 4403
        await second_socket.send(json.dumps({"type": "ping"}))
        assert await receive_type(second_socket, "pong") == {"type": "pong"}


def prepare() -> None:
    users = {
        name: User.objects.get(username=f"stage7-{name}") for name in ("alice", "bob", "outsider")
    }
    users["admin"] = User.objects.get(username="stage7-private-admin")
    previous = Conversation.objects.filter(title="Stage 8 Acceptance Group")
    PinnedMessage.objects.filter(conversation__in=previous).delete()
    for message in Message.objects.filter(conversation__in=previous).order_by("-sequence"):
        message.delete()
    previous.delete()
    clients = {name: login(str(account.username)) for name, account in users.items()}

    group = mutate(
        clients["alice"],
        "post",
        "/api/v1/messenger/conversations/group",
        {"title": "Stage 8 Acceptance Group", "member_ids": [users["bob"].pk]},
    )
    assert group.status_code == 201, group.data
    conversation_id = group.data["id"]
    messages_url = f"/api/v1/messenger/conversations/{conversation_id}/messages"
    first_client_id = str(uuid.uuid4())
    first = mutate(
        clients["alice"],
        "post",
        messages_url,
        {"client_message_id": first_client_id, "body": "Stage 8 before join"},
    )
    assert first.status_code == 201, first.data
    exact_retry = mutate(
        clients["alice"],
        "post",
        messages_url,
        {"client_message_id": first_client_id, "body": "Stage 8 before join"},
    )
    assert exact_retry.status_code == 200 and exact_retry.data["id"] == first.data["id"]
    conflict = mutate(
        clients["alice"],
        "post",
        messages_url,
        {"client_message_id": first_client_id, "body": "conflicting payload"},
    )
    assert conflict.status_code == 422, conflict.data
    assert (
        mutate(
            clients["alice"],
            "put",
            f"/api/v1/messenger/messages/{first.data['id']}/pin",
        ).status_code
        == 204
    )

    members_url = f"/api/v1/messenger/conversations/{conversation_id}/members"
    added = mutate(clients["alice"], "post", members_url, {"user_id": users["outsider"].pk})
    assert added.status_code == 201, added.data
    assert get(clients["outsider"], messages_url).data["messages"] == []
    assert (
        get(clients["outsider"], f"/api/v1/messenger/conversations/{conversation_id}").data[
            "pinned_messages"
        ]
        == []
    )

    second = mutate(
        clients["alice"],
        "post",
        messages_url,
        {
            "client_message_id": str(uuid.uuid4()),
            "body": "Stage 8 reply after join",
            "reply_to_id": first.data["id"],
        },
    )
    assert second.status_code == 201, second.data
    outsider_history = get(clients["outsider"], messages_url)
    assert [row["id"] for row in outsider_history.data["messages"]] == [second.data["id"]]
    assert outsider_history.data["messages"][0]["reply_to"] is None

    edited = mutate(
        clients["alice"],
        "patch",
        f"/api/v1/messenger/messages/{second.data['id']}",
        {"body": "Stage 8 edited searchable reply"},
    )
    assert edited.status_code == 200 and edited.data["edited_at"]
    reaction = mutate(
        clients["outsider"],
        "put",
        f"/api/v1/messenger/messages/{second.data['id']}/reaction",
        {"reaction_type": "LOVE"},
    )
    assert reaction.status_code == 200 and reaction.data["reactions"][0]["count"] == 1
    search = get(
        clients["outsider"],
        f"/api/v1/messenger/conversations/{conversation_id}/search?q=searchable",
    )
    assert [row["id"] for row in search.data["results"]] == [second.data["id"]]

    upload = mutate(
        clients["alice"],
        "post",
        f"/api/v1/messenger/conversations/{conversation_id}/attachments",
        {
            "file": SimpleUploadedFile(
                "stage8.pdf", b"%PDF-1.7\n%%EOF\n", content_type="application/pdf"
            )
        },
        multipart=True,
    )
    assert upload.status_code == 201, upload.data
    attachment = mutate(
        clients["alice"],
        "post",
        messages_url,
        {
            "client_message_id": str(uuid.uuid4()),
            "attachment_ids": [upload.data["id"]],
        },
    )
    assert attachment.status_code == 201, attachment.data
    content_url = f"/api/v1/media/{upload.data['id']}/content"
    assert get(clients["outsider"], content_url).status_code == 200
    assert get(clients["admin"], content_url).status_code == 404

    state = mutate(
        clients["alice"],
        "patch",
        f"/api/v1/messenger/conversations/{conversation_id}/state",
        {"pinned": True, "is_archived": True, "draft_body": "Stage 8 draft"},
    )
    assert state.status_code == 200, state.data
    delivered = mutate(
        clients["outsider"],
        "post",
        f"/api/v1/messenger/conversations/{conversation_id}/delivered",
        {"sequence": attachment.data["sequence"]},
    )
    read = mutate(
        clients["outsider"],
        "post",
        f"/api/v1/messenger/conversations/{conversation_id}/read",
        {"sequence": attachment.data["sequence"]},
    )
    assert delivered.status_code == 200 and read.status_code == 200

    second_device = login(str(users["alice"].username))
    asyncio.run(
        assert_session_logout(ticket(clients["alice"]), ticket(second_device), clients["alice"])
    )
    clients["alice"] = second_device
    assert (
        AuditEvent.objects.filter(
            target_type=AuditEvent.TargetType.MESSAGE,
            target_id=second.data["id"],
        ).count()
        >= 3
    )

    STATE_FILE.write_text(
        json.dumps(
            {
                "conversation_id": conversation_id,
                "alice_cookies": cookies(clients["alice"]),
                "bob_cookies": cookies(clients["bob"]),
                "outage_client_id": str(uuid.uuid4()),
                "attachment_id": upload.data["id"],
                "attachment_message_id": attachment.data["id"],
            }
        ),
        encoding="utf-8",
    )
    print(json.dumps({"phase": "prepare", "status": "PASS", "conversation_id": conversation_id}))


def outage() -> None:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    client = restore(state["alice_cookies"])
    response = mutate(
        client,
        "post",
        f"/api/v1/messenger/conversations/{state['conversation_id']}/messages",
        {
            "client_message_id": state["outage_client_id"],
            "body": "Stage 8 persisted during Redis outage",
        },
    )
    assert response.status_code == 201, response.data
    pending = RealtimeOutboxEvent.objects.filter(
        payload__message_id=response.data["id"], delivered_at__isnull=True
    ).first()
    assert pending is not None
    state["outage_message_id"] = response.data["id"]
    state["outbox_event_id"] = str(pending.pk)
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    print(json.dumps({"phase": "outage", "status": "PASS", "message_id": response.data["id"]}))


def verify() -> None:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        row = RealtimeOutboxEvent.objects.get(pk=state["outbox_event_id"])
        if row.delivered_at is not None:
            break
        time.sleep(0.5)
    else:
        raise AssertionError("Pending realtime outbox event was not delivered")

    alice = restore(state["alice_cookies"])
    bob = restore(state["bob_cookies"])
    messages_url = f"/api/v1/messenger/conversations/{state['conversation_id']}/messages"
    history = get(alice, messages_url)
    assert history.status_code == 200
    assert any(row["id"] == state["outage_message_id"] for row in history.data["messages"])
    assert get(alice, f"/api/v1/media/{state['attachment_id']}/content").status_code == 200

    removal = mutate(
        alice,
        "delete",
        f"/api/v1/messenger/conversations/{state['conversation_id']}/members/"
        f"{User.objects.get(username='stage7-bob').pk}",
    )
    assert removal.status_code == 204, removal.data
    future = mutate(
        alice,
        "post",
        messages_url,
        {"client_message_id": str(uuid.uuid4()), "body": "Stage 8 after removal"},
    )
    assert future.status_code == 201
    assert get(bob, messages_url).status_code == 404
    assert Message.objects.filter(pk=state["outage_message_id"]).exists()
    assert (
        ConversationMembership.objects.filter(
            conversation_id=state["conversation_id"], left_at__isnull=True
        ).count()
        == 2
    )
    assert timezone.now() >= Message.objects.get(pk=future.data["id"]).created_at
    STATE_FILE.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "phase": "verify",
                "status": "PASS",
                "outbox_recovered": True,
                "attachment_idor": True,
                "membership_boundary": True,
                "session_logout_scope": True,
            }
        )
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "verify"
    {"prepare": prepare, "outage": outage, "verify": verify}[mode]()
