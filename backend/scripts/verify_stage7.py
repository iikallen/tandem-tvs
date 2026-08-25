"""Real PostgreSQL/Redis/Channels acceptance for Stage 7 Messenger Core."""

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

import redis  # noqa: E402
import websockets  # noqa: E402
from django.conf import settings  # noqa: E402
from django.utils import timezone  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402
from websockets.exceptions import ConnectionClosed  # noqa: E402

from apps.identity.models import AccessGrant, User  # noqa: E402
from apps.messenger.models import (  # noqa: E402
    Conversation,
    ConversationMembership,
    DirectConversationPair,
    Message,
    PinnedMessage,
)
from apps.organization.models import OrgUnit  # noqa: E402

STATE_FILE = Path(settings.MEDIA_ROOT) / ".stage7-acceptance.json"
PASSWORD = settings.STAGE6_DEMO_PASSWORD
USERS = {
    "alice": ("stage7-alice", "Алия Stage 7"),
    "bob": ("stage7-bob", "Болат Stage 7"),
    "outsider": ("stage7-outsider", "Сара Stage 7"),
    "admin": ("stage7-private-admin", "Администратор Stage 7"),
    "no_access": ("stage7-no-access", "Нет доступа Stage 7"),
}
REQUEST_META = {"HTTP_HOST": "localhost", "HTTP_X_FORWARDED_PROTO": "https"}
ACCEPTANCE_ORIGIN = os.getenv("ACCEPTANCE_ORIGIN", "http://localhost")
ws_connect = cast(Any, websockets.connect)


def retrieve(client: APIClient, path: str):
    return cast(Any, client).get(path, **REQUEST_META)


def csrf(client: APIClient) -> str:
    response = retrieve(client, "/api/v1/auth/csrf")
    assert response.status_code == 200, response.data
    return response.data["csrf_token"]


def mutate(client: APIClient, method: str, path: str, data: dict | None = None):
    return getattr(cast(Any, client), method)(
        path,
        data or {},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(client),
        **REQUEST_META,
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
    return {key: morsel.value for key, morsel in client.cookies.items()}


def restored_client(values: dict[str, str]) -> APIClient:
    client = APIClient(enforce_csrf_checks=True)
    for key, value in values.items():
        client.cookies[key] = value
    return client


def redis_run_id() -> str:
    client = cast(Any, redis.Redis.from_url(settings.REALTIME_REDIS_URL))
    value = client.info("server")["run_id"]
    assert isinstance(value, str) and value
    return value


def backend_boot_ticks() -> str:
    return Path("/proc/1/stat").read_text(encoding="utf-8").split()[21]


def ticket(client: APIClient) -> str:
    response = mutate(
        client,
        "post",
        "/api/v1/realtime/tickets",
        {"scope": "MESSENGER"},
    )
    assert response.status_code == 200, response.data
    return response.data["ticket"]


def websocket_url(value: str) -> str:
    return f"ws://127.0.0.1:8000/ws/v1/messenger?ticket={value}"


async def receive_type(socket, event_type: str, timeout: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        event = json.loads(
            await asyncio.wait_for(socket.recv(), timeout=max(0.01, deadline - time.monotonic()))
        )
        if event.get("type") == event_type:
            return event


async def assert_realtime_message(token: str, client: APIClient, conversation_id: str) -> float:
    message_id = str(uuid.uuid4())
    async with ws_connect(
        websocket_url(token), origin=ACCEPTANCE_ORIGIN, open_timeout=5, close_timeout=2
    ) as socket:
        started = time.perf_counter()
        response = await asyncio.to_thread(
            mutate,
            client,
            "post",
            f"/api/v1/messenger/conversations/{conversation_id}/messages",
            {"client_message_id": message_id, "body": "Stage 7 realtime under one second"},
        )
        assert response.status_code == 201, response.data
        event = await receive_type(socket, "messenger.message.created", timeout=1.0)
        latency = time.perf_counter() - started
        assert event["type"] == "messenger.message.created", event
        assert event["conversation_id"] == conversation_id, event
        assert "body" not in event, event
        assert latency < 1.0, latency
        return latency


async def assert_forced_close(token: str, action) -> None:
    async with ws_connect(
        websocket_url(token), origin=ACCEPTANCE_ORIGIN, open_timeout=5, close_timeout=2
    ) as socket:
        response = await asyncio.to_thread(action)
        assert response.status_code in {200, 204}, getattr(response, "data", None)
        try:
            while True:
                await asyncio.wait_for(socket.recv(), timeout=2.0)
        except ConnectionClosed as exc:
            assert exc.code == 4403, exc.code


async def assert_reconnect(token: str) -> None:
    async with ws_connect(
        websocket_url(token), origin=ACCEPTANCE_ORIGIN, open_timeout=5, close_timeout=2
    ) as socket:
        await socket.send(json.dumps({"type": "ping"}))
        assert await receive_type(socket, "pong") == {"type": "pong"}


def setup_users() -> dict[str, User]:
    if not PASSWORD:
        raise RuntimeError("STAGE6_DEMO_PASSWORD is required")
    org_unit = cast(Any, OrgUnit).objects.get(external_id="communications")
    result: dict[str, User] = {}
    for key, (username, full_name) in USERS.items():
        user, _ = User.objects.get_or_create(username=username)
        user.full_name = full_name
        user.email = f"{username}@example.invalid"
        user.org_unit = org_unit
        user.is_active = True
        user.activated_at = timezone.now()
        user.password_changed_at = timezone.now()
        user.set_password(PASSWORD)
        user.save()
        result[key] = user

    previous = (
        cast(Any, Conversation).objects.filter(memberships__user__in=result.values()).distinct()
    )
    PinnedMessage.objects.filter(conversation__in=previous).delete()
    for message in Message.objects.filter(conversation__in=previous).order_by("-sequence"):
        message.delete()
    previous.delete()
    cast(Any, AccessGrant).objects.filter(user__in=result.values()).delete()
    actor = User.objects.get(portal_id="admin-1")
    cast(Any, AccessGrant).objects.bulk_create(
        [
            *[
                AccessGrant(
                    user=result[key],
                    module=AccessGrant.Module.MESSENGER,
                    role=AccessGrant.Role.MEMBER,
                    created_by=actor,
                )
                for key in ("alice", "bob", "outsider", "admin")
            ],
            AccessGrant(
                user=result["admin"],
                module=AccessGrant.Module.PLATFORM,
                role=AccessGrant.Role.ADMIN,
                created_by=actor,
            ),
            AccessGrant(
                user=result["no_access"],
                module=AccessGrant.Module.NEWS,
                role=AccessGrant.Role.MEMBER,
                created_by=actor,
            ),
        ]
    )
    return result


def assert_private(response) -> None:
    assert response.status_code == 404, response.data


def prepare() -> None:
    from django.core.management import call_command

    call_command("seed_stage2_demo", verbosity=0)
    call_command("seed_stage3_demo", verbosity=0)
    users = setup_users()
    clients = {key: login(str(user.username)) for key, user in users.items()}

    no_access = retrieve(clients["no_access"], "/api/v1/messenger/conversations")
    assert no_access.status_code == 403, no_access.data
    people = retrieve(clients["alice"], "/api/v1/messenger/people?search=Stage%207")
    assert people.status_code == 200, people.data
    people_ids = {row["id"] for row in people.data}
    assert users["bob"].pk in people_ids and users["no_access"].pk not in people_ids

    direct = mutate(
        clients["alice"],
        "post",
        "/api/v1/messenger/conversations/direct",
        {"user_id": users["bob"].pk},
    )
    assert direct.status_code == 201, direct.data
    direct_id = direct.data["id"]
    reverse = mutate(
        clients["bob"],
        "post",
        "/api/v1/messenger/conversations/direct",
        {"user_id": users["alice"].pk},
    )
    assert reverse.status_code == 200 and reverse.data["id"] == direct_id, reverse.data
    assert cast(Any, DirectConversationPair).objects.filter(conversation_id=direct_id).count() == 1
    self_chat = mutate(
        clients["alice"],
        "post",
        "/api/v1/messenger/conversations/direct",
        {"user_id": users["alice"].pk},
    )
    assert self_chat.status_code == 400, self_chat.data

    group = mutate(
        clients["alice"],
        "post",
        "/api/v1/messenger/conversations/group",
        {
            "title": "Stage 7 Acceptance Group",
            "member_ids": [users["bob"].pk, users["outsider"].pk],
        },
    )
    assert group.status_code == 201, group.data
    group_id = group.data["id"]
    group_members = retrieve(
        clients["alice"], f"/api/v1/messenger/conversations/{group_id}/members"
    )
    assert (
        next(
            row for row in group_members.data["results"] if row["user"]["id"] == users["alice"].pk
        )["role"]
        == "ADMIN"
    )

    for key in ("outsider", "admin"):
        assert_private(retrieve(clients[key], f"/api/v1/messenger/conversations/{direct_id}"))
        assert_private(
            retrieve(clients[key], f"/api/v1/messenger/conversations/{direct_id}/messages")
        )
        assert_private(
            mutate(
                clients[key],
                "post",
                f"/api/v1/messenger/conversations/{direct_id}/messages",
                {"client_message_id": str(uuid.uuid4()), "body": "forbidden"},
            )
        )

    ids = [str(uuid.uuid4()) for _ in range(4)]
    saved = []
    for index, client_id in enumerate(ids):
        response = mutate(
            clients["alice"],
            "post",
            f"/api/v1/messenger/conversations/{direct_id}/messages",
            {"client_message_id": client_id, "body": f"Ordered message {index + 1}"},
        )
        assert response.status_code == 201, response.data
        saved.append(response.data)
    retry = mutate(
        clients["alice"],
        "post",
        f"/api/v1/messenger/conversations/{direct_id}/messages",
        {"client_message_id": ids[-1], "body": "Ordered message 4"},
    )
    assert retry.status_code == 200 and retry.data["id"] == saved[-1]["id"], retry.data
    conflict = mutate(
        clients["alice"],
        "post",
        f"/api/v1/messenger/conversations/{direct_id}/messages",
        {"client_message_id": ids[-1], "body": "must not replace persisted body"},
    )
    assert conflict.status_code == 422, conflict.data
    assert [row["sequence"] for row in saved] == sorted(row["sequence"] for row in saved)
    assert (
        cast(Any, Message)
        .objects.filter(conversation_id=direct_id, client_message_id=ids[-1])
        .count()
        == 1
    )

    page = retrieve(
        clients["bob"],
        f"/api/v1/messenger/conversations/{direct_id}/messages?page_size=2",
    )
    assert page.status_code == 200 and len(page.data["messages"]) == 2, page.data
    assert page.data["has_more"] and page.data["next_before_sequence"]
    inbox = retrieve(clients["bob"], "/api/v1/messenger/conversations")
    direct_inbox = next(row for row in inbox.data["results"] if row["id"] == direct_id)
    assert direct_inbox["unread_count"] >= 4, direct_inbox
    read = mutate(
        clients["bob"],
        "post",
        f"/api/v1/messenger/conversations/{direct_id}/read",
        {"sequence": saved[-1]["sequence"]},
    )
    assert read.status_code == 200, read.data
    backwards = mutate(
        clients["bob"],
        "post",
        f"/api/v1/messenger/conversations/{direct_id}/read",
        {"sequence": 1},
    )
    assert backwards.status_code == 200
    assert backwards.data["last_read_sequence"] == saved[-1]["sequence"]
    receipts = retrieve(clients["alice"], f"/api/v1/messenger/conversations/{direct_id}/messages")
    assert receipts.data["messages"][-1]["receipt"]["read"] is True

    group_message = mutate(
        clients["alice"],
        "post",
        f"/api/v1/messenger/conversations/{group_id}/messages",
        {"client_message_id": str(uuid.uuid4()), "body": "Group receipt"},
    )
    assert group_message.status_code == 201, group_message.data
    for key in ("bob", "outsider"):
        response = mutate(
            clients[key],
            "post",
            f"/api/v1/messenger/conversations/{group_id}/read",
            {"sequence": group_message.data["sequence"]},
        )
        assert response.status_code == 200, response.data
    group_history = retrieve(
        clients["alice"], f"/api/v1/messenger/conversations/{group_id}/messages"
    )
    receipt = group_history.data["messages"][-1]["receipt"]
    assert receipt["read_count"] == 2 and receipt["recipient_count"] == 2, receipt

    realtime_latency = asyncio.run(
        assert_realtime_message(ticket(clients["bob"]), clients["alice"], direct_id)
    )

    revoke_path = f"/api/v1/platform/users/{users['bob'].pk}/grants/MESSENGER/MEMBER"
    old_epoch = int(cast(Any, users["bob"].security_epoch))
    asyncio.run(
        assert_forced_close(
            ticket(clients["bob"]),
            lambda: mutate(clients["admin"], "delete", revoke_path),
        )
    )
    users["bob"].refresh_from_db()
    assert users["bob"].security_epoch == old_epoch + 1
    denied = retrieve(clients["bob"], f"/api/v1/messenger/conversations/{direct_id}/messages")
    assert denied.status_code in {401, 403}, denied.data
    denied_ticket = mutate(
        clients["bob"], "post", "/api/v1/realtime/tickets", {"scope": "MESSENGER"}
    )
    assert denied_ticket.status_code in {401, 403}, denied_ticket.data
    assert mutate(clients["admin"], "put", revoke_path).status_code == 204
    clients["bob"] = login(str(users["bob"].username))

    asyncio.run(
        assert_forced_close(
            ticket(clients["bob"]),
            lambda: mutate(
                clients["admin"],
                "patch",
                f"/api/v1/platform/users/{users['bob'].pk}",
                {"is_active": False},
            ),
        )
    )
    assert (
        mutate(
            clients["admin"],
            "patch",
            f"/api/v1/platform/users/{users['bob'].pk}",
            {"is_active": True},
        ).status_code
        == 200
    )
    clients["bob"] = login(str(users["bob"].username))

    STATE_FILE.write_text(
        json.dumps(
            {
                "redis_run_id": redis_run_id(),
                "backend_boot_ticks": backend_boot_ticks(),
                "direct_id": direct_id,
                "group_id": group_id,
                "alice_id": users["alice"].pk,
                "bob_id": users["bob"].pk,
                "alice_cookies": cookies(clients["alice"]),
                "bob_cookies": cookies(clients["bob"]),
                "outage_client_id": str(uuid.uuid4()),
                "realtime_latency_seconds": realtime_latency,
            }
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "phase": "prepare",
                "status": "PASS",
                "direct_id": direct_id,
                "group_id": group_id,
                "realtime_latency_seconds": round(realtime_latency, 4),
                "privacy": True,
                "revocation": True,
            }
        )
    )


def outage() -> None:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    client = restored_client(state["alice_cookies"])
    response = mutate(
        client,
        "post",
        f"/api/v1/messenger/conversations/{state['direct_id']}/messages",
        {
            "client_message_id": state["outage_client_id"],
            "body": "Persisted while Redis was unavailable",
        },
    )
    assert response.status_code == 201, response.data
    state["outage_message_id"] = response.data["id"]
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    assert cast(Any, Message).objects.filter(pk=response.data["id"]).exists()
    print(
        json.dumps(
            {
                "phase": "outage",
                "status": "PASS",
                "postgres_commit": True,
                "outage_message_id": response.data["id"],
            }
        )
    )


def verify() -> None:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    assert redis_run_id() != state["redis_run_id"], "Redis was not restarted"
    assert backend_boot_ticks() != state["backend_boot_ticks"], "Backend was not restarted"
    client = restored_client(state["bob_cookies"])
    session = retrieve(client, "/api/v1/auth/session")
    assert session.status_code == 200 and session.data["authenticated"] is True, session.data
    history = retrieve(client, f"/api/v1/messenger/conversations/{state['direct_id']}/messages")
    assert history.status_code == 200, history.data
    assert any(row["id"] == state["outage_message_id"] for row in history.data["messages"])
    assert (
        cast(Any, Message)
        .objects.filter(pk=state["outage_message_id"], conversation_id=state["direct_id"])
        .exists()
    )
    asyncio.run(assert_reconnect(ticket(client)))
    assert (
        cast(Any, ConversationMembership)
        .objects.filter(conversation_id=state["direct_id"], user_id=state["bob_id"])
        .exists()
    )
    assert cast(Any, Conversation).objects.filter(pk=state["group_id"]).exists()
    STATE_FILE.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "phase": "verify",
                "status": "PASS",
                "redis_restarted": True,
                "backend_restarted": True,
                "message_survived_redis_outage": True,
                "history_survived_backend_restart": True,
                "reconnect_synchronized": True,
            }
        )
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "verify"
    {"prepare": prepare, "outage": outage, "verify": verify}[mode]()
