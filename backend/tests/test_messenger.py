import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing.websocket import WebsocketCommunicator
from django.contrib.sessions.backends.db import SessionStore
from django.db import close_old_connections, connection, connections
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.test import APIClient

from apps.identity.models import AccessGrant, User
from apps.messenger.events import membership_changed_after_commit
from apps.messenger.models import (
    Conversation,
    ConversationMembership,
    DirectConversationPair,
    Message,
)
from apps.messenger.serializers import MessageBodyField
from apps.messenger.services import create_direct_conversation, send_message
from apps.realtime.claims import RealtimeScope, RealtimeTicket
from apps.realtime.groups import conversation_group, messenger_user_group, user_control_group
from apps.realtime.models import RealtimeOutboxEvent
from apps.realtime.session_security import session_fingerprint
from config.asgi import application


def messenger_user(username: str, *, active: bool = True, platform_admin: bool = False) -> User:
    user = User.objects.create(username=username, full_name=username.title(), is_active=active)
    AccessGrant.objects.create(user=user, module="MESSENGER", role="MEMBER")
    if platform_admin:
        AccessGrant.objects.create(user=user, module="PLATFORM", role="ADMIN")
    return user


def client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def realtime_claims(user: User) -> RealtimeTicket:
    session = SessionStore()
    session["_auth_user_id"] = str(user.pk)
    session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
    session["security_epoch"] = user.security_epoch
    session.save()
    assert session.session_key
    return RealtimeTicket(
        user_id=user.pk,
        security_epoch=user.security_epoch,
        session_key=session.session_key,
        session_fingerprint=session_fingerprint(session.session_key),
        scope=RealtimeScope.MESSENGER,
    )


def direct(client: APIClient, other: User):
    response = client.post(
        "/api/v1/messenger/conversations/direct", {"user_id": other.pk}, format="json"
    )
    assert response.status_code in {200, 201}, response.data
    return response


@pytest.mark.django_db
def test_people_and_direct_creation_are_local_filtered_idempotent_and_ordered():
    alice = messenger_user("alice")
    bob = messenger_user("bob")
    inactive = messenger_user("inactive", active=False)
    no_access = User.objects.create(username="no-access", full_name="No Access")
    client = client_for(alice)

    people = client.get("/api/v1/messenger/people?search=bo")
    assert people.status_code == 200
    assert [person["id"] for person in people.data] == [bob.pk]
    assert inactive.pk not in {
        person["id"] for person in client.get("/api/v1/messenger/people").data
    }
    assert no_access.pk not in {
        person["id"] for person in client.get("/api/v1/messenger/people").data
    }

    created = direct(client, bob)
    reverse = direct(client_for(bob), alice)
    assert created.status_code == 201
    assert reverse.status_code == 200
    assert created.data["id"] == reverse.data["id"]
    pair = DirectConversationPair.objects.get()
    assert pair.user_low.pk == min(alice.pk, bob.pk)
    assert pair.user_high.pk == max(alice.pk, bob.pk)
    assert pair.conversation.memberships.count() == 2


@pytest.mark.django_db
def test_direct_rejects_self_inactive_and_missing_access():
    alice = messenger_user("alice-denials")
    inactive = messenger_user("inactive-denials", active=False)
    no_access = User.objects.create(username="no-access-denials", full_name="No access")
    client = client_for(alice)
    assert (
        client.post(
            "/api/v1/messenger/conversations/direct", {"user_id": alice.pk}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/messenger/conversations/direct", {"user_id": inactive.pk}, format="json"
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/messenger/conversations/direct", {"user_id": no_access.pk}, format="json"
        ).status_code
        == 404
    )


@pytest.mark.django_db(transaction=True)
def test_parallel_direct_creation_produces_one_conversation():
    alice = messenger_user("parallel-alice")
    bob = messenger_user("parallel-bob")

    def create(left_id: int, right_id: int):
        close_old_connections()
        try:
            left = User.objects.get(pk=left_id)
            right = User.objects.get(pk=right_id)
            return create_direct_conversation(left, right)[0].pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda pair: create(*pair), [(alice.pk, bob.pk), (bob.pk, alice.pk)]))
    assert ids[0] == ids[1]
    assert Conversation.objects.count() == 1
    assert DirectConversationPair.objects.count() == 1


@pytest.mark.django_db
def test_group_roles_membership_and_private_idor():
    creator = messenger_user("group-creator")
    member = messenger_user("group-member")
    outsider = messenger_user("group-outsider")
    platform_admin = messenger_user("group-platform-admin", platform_admin=True)
    response = client_for(creator).post(
        "/api/v1/messenger/conversations/group",
        {"title": "Portal team", "member_ids": [member.pk]},
        format="json",
    )
    assert response.status_code == 201, response.data
    conversation_id = response.data["id"]
    roles = dict(
        ConversationMembership.objects.filter(conversation_id=conversation_id).values_list(
            "user_id", "role"
        )
    )
    assert roles == {
        creator.pk: ConversationMembership.Role.ADMIN,
        member.pk: ConversationMembership.Role.MEMBER,
    }
    assert (
        client_for(member).get(f"/api/v1/messenger/conversations/{conversation_id}").status_code
        == 200
    )
    for user in (outsider, platform_admin):
        client = client_for(user)
        assert client.get(f"/api/v1/messenger/conversations/{conversation_id}").status_code == 404
        assert (
            client.get(f"/api/v1/messenger/conversations/{conversation_id}/messages").status_code
            == 404
        )
        assert (
            client.post(
                f"/api/v1/messenger/conversations/{conversation_id}/messages",
                {"client_message_id": str(uuid.uuid4()), "body": "forbidden"},
                format="json",
            ).status_code
            == 404
        )


@pytest.mark.django_db
def test_group_rejects_ineligible_duplicate_and_creator_only_members():
    creator = messenger_user("invalid-group-creator")
    member = messenger_user("invalid-group-member")
    no_access = User.objects.create(username="invalid-group-none", full_name="None")
    client = client_for(creator)
    path = "/api/v1/messenger/conversations/group"
    assert (
        client.post(path, {"title": "No", "member_ids": [creator.pk]}, format="json").status_code
        == 400
    )
    assert (
        client.post(
            path, {"title": "No", "member_ids": [member.pk, member.pk]}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(path, {"title": "No", "member_ids": [no_access.pk]}, format="json").status_code
        == 400
    )


@pytest.mark.django_db
def test_message_sequence_idempotency_body_and_history_pagination():
    alice = messenger_user("message-alice")
    bob = messenger_user("message-bob")
    conversation_id = direct(client_for(alice), bob).data["id"]
    path = f"/api/v1/messenger/conversations/{conversation_id}/messages"
    client = client_for(alice)
    client_id = str(uuid.uuid4())
    first = client.post(path, {"client_message_id": client_id, "body": " A\x00B "}, format="json")
    retry = client.post(path, {"client_message_id": client_id, "body": " A\x00B "}, format="json")
    conflict = client.post(
        path, {"client_message_id": client_id, "body": "different"}, format="json"
    )
    second = client.post(
        path, {"client_message_id": str(uuid.uuid4()), "body": "Second"}, format="json"
    )
    assert first.status_code == 201 and retry.status_code == 200 and second.status_code == 201
    assert conflict.status_code == 422
    assert first.data["id"] == retry.data["id"]
    assert first.data["body"] == "AB"
    assert list(Message.objects.values_list("sequence", flat=True)) == [1, 2]
    assert client.get("/api/v1/messenger/conversations").data["results"][0]["unread_count"] == 0
    page = client.get(f"{path}?page_size=1")
    assert [item["sequence"] for item in page.data["messages"]] == [2]
    assert page.data["has_more"] is True
    older = client.get(f"{path}?page_size=1&before_sequence={page.data['next_before_sequence']}")
    assert [item["sequence"] for item in older.data["messages"]] == [1]
    assert client.get(f"{path}?page_size=51").status_code == 400
    assert client.get(f"{path}?before_sequence=invalid").status_code == 400
    assert (
        client.post(
            path, {"client_message_id": str(uuid.uuid4()), "body": "\x00\x01"}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(
            path, {"client_message_id": str(uuid.uuid4()), "body": "x" * 10_001}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(
            path,
            {"client_message_id": str(uuid.uuid4()), "body": "valid", "author": bob.pk},
            format="json",
        ).status_code
        == 400
    )
    with pytest.raises(DRFValidationError):
        MessageBodyField().to_internal_value(7)
    assert MessageBodyField().to_representation("body") == "body"


@pytest.mark.django_db(transaction=True)
def test_parallel_messages_have_unique_strict_sequences():
    alice = messenger_user("sequence-alice")
    bob = messenger_user("sequence-bob")
    conversation, _ = create_direct_conversation(alice, bob)

    def create_message(number: int):
        close_old_connections()
        try:
            local_conversation = Conversation.objects.get(pk=conversation.pk)
            local_author = User.objects.get(pk=alice.pk)
            return send_message(
                local_conversation,
                author=local_author,
                client_message_id=uuid.uuid4(),
                body=f"Message {number}",
            )[0].sequence
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=6) as pool:
        sequences = sorted(pool.map(create_message, range(12)))
    assert sequences == list(range(1, 13))
    conversation.refresh_from_db()
    assert conversation.last_sequence == 12


@pytest.mark.django_db
def test_read_pointer_unread_and_receipts():
    alice = messenger_user("read-alice")
    bob = messenger_user("read-bob")
    conversation_id = direct(client_for(alice), bob).data["id"]
    messages_path = f"/api/v1/messenger/conversations/{conversation_id}/messages"
    for body in ("One", "Two", "Three"):
        assert (
            client_for(alice)
            .post(
                messages_path,
                {"client_message_id": str(uuid.uuid4()), "body": body},
                format="json",
            )
            .status_code
            == 201
        )
    bob_client = client_for(bob)
    inbox = bob_client.get("/api/v1/messenger/conversations")
    assert inbox.data["results"][0]["unread_count"] == 3
    read_path = f"/api/v1/messenger/conversations/{conversation_id}/read"
    assert bob_client.post(read_path, {"sequence": 2}, format="json").status_code == 200
    assert (
        bob_client.post(read_path, {"sequence": 1}, format="json").data["last_read_sequence"] == 2
    )
    assert bob_client.post(read_path, {"sequence": 4}, format="json").status_code == 400
    history = client_for(alice).get(messages_path)
    assert history.data["messages"][0]["receipt"] == {
        "delivered_count": 1,
        "read_count": 1,
        "recipient_count": 1,
        "delivered": True,
        "read": True,
    }
    assert history.data["messages"][2]["receipt"]["read"] is False
    assert bob_client.get("/api/v1/messenger/conversations").data["results"][0]["unread_count"] == 1


@pytest.mark.django_db
def test_group_read_count_excludes_author():
    author = messenger_user("receipt-author")
    reader = messenger_user("receipt-reader")
    unread = messenger_user("receipt-unread")
    group = (
        client_for(author)
        .post(
            "/api/v1/messenger/conversations/group",
            {"title": "Receipts", "member_ids": [reader.pk, unread.pk]},
            format="json",
        )
        .data
    )
    path = f"/api/v1/messenger/conversations/{group['id']}/messages"
    message = (
        client_for(author)
        .post(
            path,
            {"client_message_id": str(uuid.uuid4()), "body": "Read me"},
            format="json",
        )
        .data
    )
    client_for(reader).post(
        f"/api/v1/messenger/conversations/{group['id']}/read",
        {"sequence": message["sequence"]},
        format="json",
    )
    receipt = client_for(author).get(path).data["messages"][0]["receipt"]
    assert receipt == {"delivered_count": 1, "read_count": 1, "recipient_count": 2}


@pytest.mark.django_db
def test_no_grant_is_denied_and_inbox_is_bounded_to_ten_queries():
    denied = User.objects.create(username="messenger-denied", full_name="Denied")
    assert client_for(denied).get("/api/v1/messenger/conversations").status_code == 403
    owner = messenger_user("inbox-owner")
    for number in range(50):
        peer = messenger_user(f"inbox-peer-{number:02}")
        conversation, _ = create_direct_conversation(owner, peer)
        send_message(
            conversation,
            author=peer,
            client_message_id=uuid.uuid4(),
            body=f"Message {number}",
        )
    with CaptureQueriesContext(connection) as queries:
        response = client_for(owner).get("/api/v1/messenger/conversations")
    assert response.status_code == 200 and len(response.data["results"]) == 30
    assert len(queries) <= 10, [query["sql"] for query in queries]
    seen = {row["id"] for row in response.data["results"]}
    while response.data["next"]:
        response = client_for(owner).get(response.data["next"])
        seen.update(row["id"] for row in response.data["results"])
    assert len(seen) == 50


@pytest.mark.django_db(transaction=True)
def test_messenger_ticket_socket_events_are_hints_and_invalidation_closes(monkeypatch):
    alice = messenger_user("socket-alice")
    bob = messenger_user("socket-bob")
    conversation, _ = create_direct_conversation(alice, bob)
    claims = realtime_claims(bob)
    monkeypatch.setattr("apps.realtime.middleware.consume_ticket", lambda _token: claims)

    async def scenario():
        socket = WebsocketCommunicator(
            application,
            "/ws/v1/messenger?ticket=valid",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await socket.connect(timeout=3)
        assert connected
        assert await socket.receive_json_from(timeout=5) == {
            "type": "messenger.presence.changed",
            "user_id": bob.pk,
            "online": True,
        }
        await socket.send_json_to({"type": "ping"})
        assert await socket.receive_json_from(timeout=5) == {"type": "pong"}
        await socket.send_json_to(
            {
                "type": "typing",
                "conversation_id": str(conversation.pk),
                "is_typing": True,
            }
        )
        assert await socket.receive_json_from(timeout=5) == {
            "type": "messenger.typing.started",
            "conversation_id": str(conversation.pk),
            "user_id": bob.pk,
            "is_typing": True,
        }
        await asyncio.sleep(0.51)
        await socket.send_json_to(
            {
                "type": "typing",
                "conversation_id": str(conversation.pk),
                "is_typing": False,
            }
        )
        assert await socket.receive_json_from(timeout=5) == {
            "type": "messenger.typing.stopped",
            "conversation_id": str(conversation.pk),
            "user_id": bob.pk,
            "is_typing": False,
        }
        layer = get_channel_layer()
        assert layer is not None
        event = {
            "version": 2,
            "event_id": str(uuid.uuid4()),
            "type": "messenger.message.created",
            "conversation_id": str(conversation.pk),
            "message_id": str(uuid.uuid4()),
            "sequence": 1,
            "occurred_at": "2026-08-24T00:00:00Z",
        }
        await layer.group_send(
            conversation_group(conversation.pk),
            {"type": "messenger.message.created", "event": event},
        )
        assert await socket.receive_json_from(timeout=5) == event
        assert "body" not in event
        added_conversation_id = uuid.uuid4()
        added = {
            **event,
            "event_id": str(uuid.uuid4()),
            "type": "messenger.membership.added",
            "conversation_id": str(added_conversation_id),
            "user_id": bob.pk,
        }
        await layer.group_send(
            messenger_user_group(bob.pk),
            {"type": "messenger.membership.added", "event": added},
        )
        assert await socket.receive_json_from(timeout=5) == added
        read = {
            **added,
            "event_id": str(uuid.uuid4()),
            "type": "messenger.read.changed",
            "sequence": 1,
        }
        await layer.group_send(
            conversation_group(added_conversation_id),
            {"type": "messenger.read.changed", "event": read},
        )
        assert await socket.receive_json_from(timeout=5) == read
        removed = {**added, "event_id": str(uuid.uuid4()), "type": "messenger.membership.removed"}
        await layer.group_send(
            messenger_user_group(bob.pk),
            {"type": "messenger.membership.removed", "event": removed},
        )
        assert await socket.receive_json_from(timeout=5) == removed
        await layer.group_send(user_control_group(bob.pk), {"type": "auth.invalidate"})
        assert await socket.receive_output(timeout=5) == {
            "type": "websocket.close",
            "code": 4403,
        }
        await socket.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_messenger_socket_rejects_bad_ticket_input_and_expires(settings, monkeypatch):
    user = messenger_user("socket-branches")
    claims = realtime_claims(user)
    monkeypatch.setattr(
        "apps.realtime.middleware.consume_ticket",
        lambda token: claims if token == "valid" else None,
    )

    async def scenario():
        denied = WebsocketCommunicator(
            application,
            "/ws/v1/messenger?ticket=bad",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, code = await denied.connect(timeout=3)
        assert not connected and code == 4403

        for invalid in ("not-json", '{"type":"mutation"}'):
            socket = WebsocketCommunicator(
                application,
                "/ws/v1/messenger?ticket=valid",
                headers=[(b"origin", b"http://localhost")],
            )
            connected, _ = await socket.connect(timeout=3)
            assert connected
            await socket.send_to(text_data=invalid)
            assert await socket.receive_output(timeout=5) == {
                "type": "websocket.close",
                "code": 4400,
            }
            await socket.disconnect()

        invalid_uuid = WebsocketCommunicator(
            application,
            "/ws/v1/messenger?ticket=valid",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await invalid_uuid.connect(timeout=3)
        assert connected
        await invalid_uuid.send_json_to(
            {"type": "typing", "conversation_id": "invalid", "is_typing": True}
        )
        assert await invalid_uuid.receive_output(timeout=5) == {
            "type": "websocket.close",
            "code": 4400,
        }
        await invalid_uuid.disconnect()

        unauthorized = WebsocketCommunicator(
            application,
            "/ws/v1/messenger?ticket=valid",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await unauthorized.connect(timeout=3)
        assert connected
        await unauthorized.send_json_to(
            {
                "type": "typing",
                "conversation_id": str(uuid.uuid4()),
                "is_typing": True,
            }
        )
        assert await unauthorized.receive_output(timeout=5) == {
            "type": "websocket.close",
            "code": 4403,
        }
        await unauthorized.disconnect()

        binary = WebsocketCommunicator(
            application,
            "/ws/v1/messenger?ticket=valid",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await binary.connect(timeout=3)
        assert connected
        await binary.send_to(bytes_data=b"forbidden")
        assert await binary.receive_output(timeout=5) == {
            "type": "websocket.close",
            "code": 4400,
        }
        await binary.disconnect()

        settings.REALTIME_SOCKET_LIFETIME_SECONDS = 0
        expiring = WebsocketCommunicator(
            application,
            "/ws/v1/messenger?ticket=valid",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await expiring.connect(timeout=3)
        assert connected
        assert await expiring.receive_output(timeout=5) == {
            "type": "websocket.close",
            "code": 4000,
        }
        await expiring.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_membership_event_and_model_strings(monkeypatch):
    alice = messenger_user("string-alice")
    bob = messenger_user("string-bob")
    conversation, _ = create_direct_conversation(alice, bob)
    pair = DirectConversationPair.objects.get(conversation=conversation)
    membership = ConversationMembership.objects.get(conversation=conversation, user=alice)
    message, _ = send_message(
        conversation,
        author=alice,
        client_message_id=uuid.uuid4(),
        body="String",
    )
    assert str(conversation).startswith("DIRECT ")
    assert str(pair) == f"{pair.user_low.pk}:{pair.user_high.pk}"
    assert str(membership) == f"{conversation.pk}: {alice.pk}"
    assert str(message) == f"{conversation.pk}#1"

    sent = []

    class Layer:
        async def group_send(self, group, event):
            sent.append((group, event))

    monkeypatch.setattr("apps.realtime.outbox.get_channel_layer", lambda: Layer())
    membership_changed_after_commit("messenger.membership.added", conversation.pk, bob.pk)
    assert sent[0][0] == messenger_user_group(bob.pk)
    assert sent[0][1]["event"]["type"] == "messenger.membership.added"


@pytest.mark.django_db(transaction=True)
def test_redis_event_failure_cannot_rollback_message(monkeypatch):
    alice = messenger_user("redis-alice")
    bob = messenger_user("redis-bob")
    conversation, _ = create_direct_conversation(alice, bob)

    class FailingLayer:
        async def group_send(self, _group, _event):
            raise RuntimeError("Redis unavailable")

    monkeypatch.setattr("apps.realtime.outbox.get_channel_layer", lambda: FailingLayer())
    message, created = send_message(
        conversation,
        author=alice,
        client_message_id=uuid.uuid4(),
        body="Persist despite Redis",
    )
    assert created is True
    assert Message.objects.filter(pk=message.pk, body="Persist despite Redis").exists()
    assert RealtimeOutboxEvent.objects.filter(delivered_at__isnull=True).exists()


@pytest.mark.django_db
def test_ticket_endpoint_requires_messenger_grant_and_returns_scoped_ticket(monkeypatch):
    allowed = messenger_user("ticket-allowed")
    denied = User.objects.create(username="ticket-denied", full_name="Denied")
    observed: dict[str, Any] = {}

    def fake_ticket(**kwargs):
        observed.update(kwargs)
        return "token", 30

    monkeypatch.setattr("apps.discussions.views.create_realtime_ticket", fake_ticket)
    response = client_for(allowed).post(
        "/api/v1/realtime/tickets", {"scope": "MESSENGER"}, format="json"
    )
    assert response.status_code == 200 and response.data == {"ticket": "token", "expires_in": 30}
    session_key = observed.pop("session_key")
    assert session_key
    assert observed == {
        "user_id": allowed.pk,
        "security_epoch": allowed.security_epoch,
        "scope": RealtimeScope.MESSENGER,
    }
    assert (
        client_for(denied)
        .post("/api/v1/realtime/tickets", {"scope": "MESSENGER"}, format="json")
        .status_code
        == 403
    )
