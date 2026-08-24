import asyncio
from datetime import timedelta
from typing import Any, cast

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing.websocket import WebsocketCommunicator
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.discussions.events import publication_group
from apps.discussions.tickets import TicketClaims, consume_ticket, create_ticket
from apps.identity.models import User
from apps.publications.models import AudienceRule, Category, Publication
from config.asgi import application


def make_publication(settings):
    client = APIClient()
    settings.MOCK_PORTAL_USER_ID = "employee-1"
    assert client.get("/api/v1/me").status_code == 200
    user = User.objects.get(portal_id="employee-1")
    category = Category.objects.create(slug="realtime", name="Realtime")
    publication = Publication.objects.create(
        title="Realtime",
        slug="realtime",
        summary="Realtime",
        body={"type": "doc", "content": [{"type": "paragraph", "content": []}]},
        category=category,
        author=user,
        status=Publication.Status.PUBLISHED,
        published_at=timezone.now() - timedelta(minutes=1),
    )
    AudienceRule.objects.create(publication=publication, kind=AudienceRule.Kind.ALL)
    return user, publication


class FakeRedis:
    def __init__(self):
        self.values = {}

    def set(self, key, value, ex, nx):
        self.values[key] = value
        return True

    def getdel(self, key):
        return self.values.pop(key, None)


def test_ticket_is_hashed_scoped_and_one_time(settings, monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("apps.discussions.tickets._client", lambda: fake)
    token, ttl = create_ticket(user_id=7, publication_id="publication")
    assert ttl == 30
    assert token not in next(iter(fake.values))
    assert consume_ticket(token) == TicketClaims(user_id=7, publication_id="publication")
    assert consume_ticket(token) is None
    assert consume_ticket("") is None
    fake.values["realtime-ticket:bad"] = "not-json"
    monkeypatch.setattr("apps.discussions.tickets._key", lambda token: "realtime-ticket:bad")
    assert consume_ticket("corrupt") is None


@pytest.mark.django_db(transaction=True)
def test_ticket_scope_replay_visibility_lifetime_and_group_cleanup(settings, monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("apps.discussions.tickets._client", lambda: fake)
    user, publication = make_publication(settings)
    second = Publication.objects.create(
        title="Second realtime publication",
        slug="second-realtime-publication",
        summary="Second",
        body={"type": "doc", "content": [{"type": "paragraph", "content": []}]},
        category=publication.category,
        author=user,
        status=Publication.Status.PUBLISHED,
        published_at=timezone.now() - timedelta(minutes=1),
    )
    AudienceRule.objects.create(publication=second, kind=AudienceRule.Kind.ALL)

    wrong_scope, _ = create_ticket(user_id=user.pk, publication_id=publication.pk)

    async def wrong_publication():
        socket = WebsocketCommunicator(
            application,
            f"/ws/v1/publications/{second.pk}?ticket={wrong_scope}",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, code = await socket.connect()
        assert not connected and code == 4403

    async_to_sync(wrong_publication)()

    one_time, _ = create_ticket(user_id=user.pk, publication_id=publication.pk)

    async def replay_and_cleanup():
        group = publication_group(publication.pk)
        first = WebsocketCommunicator(
            application,
            f"/ws/v1/publications/{publication.pk}?ticket={one_time}",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await first.connect()
        assert connected
        layer = get_channel_layer()
        assert layer is not None
        memory_layer = cast(Any, layer)
        assert group in memory_layer.groups
        await first.disconnect()
        await asyncio.sleep(0)
        assert group not in memory_layer.groups

        replay = WebsocketCommunicator(
            application,
            f"/ws/v1/publications/{publication.pk}?ticket={one_time}",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, code = await replay.connect()
        assert not connected and code == 4403

    async_to_sync(replay_and_cleanup)()

    publication.audience_rules.all().delete()
    AudienceRule.objects.create(
        publication=publication,
        kind=AudienceRule.Kind.ORG_UNIT,
        org_unit_id="engineering",
    )
    invisible, _ = create_ticket(user_id=user.pk, publication_id=publication.pk)

    async def denied(token):
        socket = WebsocketCommunicator(
            application,
            f"/ws/v1/publications/{publication.pk}?ticket={token}",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, code = await socket.connect()
        assert not connected and code == 4403

    async_to_sync(denied)(invisible)

    publication.audience_rules.all().delete()
    AudienceRule.objects.create(publication=publication, kind=AudienceRule.Kind.ALL)
    user.is_active = False
    user.save(update_fields=["is_active"])
    blocked, _ = create_ticket(user_id=user.pk, publication_id=publication.pk)
    async_to_sync(denied)(blocked)

    user.is_active = True
    user.save(update_fields=["is_active"])
    settings.REALTIME_SOCKET_LIFETIME_SECONDS = 0
    expiring, _ = create_ticket(user_id=user.pk, publication_id=publication.pk)

    async def finite_lifetime():
        socket = WebsocketCommunicator(
            application,
            f"/ws/v1/publications/{publication.pk}?ticket={expiring}",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await socket.connect()
        assert connected
        assert await socket.receive_output(timeout=1) == {
            "type": "websocket.close",
            "code": 4000,
        }
        await socket.disconnect()

    async_to_sync(finite_lifetime)()


@pytest.mark.django_db(transaction=True)
def test_websocket_origin_ticket_scope_event_and_read_only(settings, monkeypatch):
    user, publication = make_publication(settings)
    claims = TicketClaims(user_id=user.pk, publication_id=str(publication.pk))
    monkeypatch.setattr(
        "apps.discussions.middleware.consume_ticket",
        lambda token: claims if token == "valid" else None,
    )

    async def scenario():
        denied_origin = WebsocketCommunicator(
            application,
            f"/ws/v1/publications/{publication.pk}?ticket=valid",
            headers=[(b"origin", b"https://evil.example")],
        )
        connected, _ = await denied_origin.connect()
        assert not connected

        wrong_ticket = WebsocketCommunicator(
            application,
            f"/ws/v1/publications/{publication.pk}?ticket=wrong",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, code = await wrong_ticket.connect()
        assert not connected and code == 4403

        socket = WebsocketCommunicator(
            application,
            f"/ws/v1/publications/{publication.pk}?ticket=valid",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await socket.connect()
        assert connected
        await socket.send_json_to({"type": "ping"})
        assert await socket.receive_json_from() == {"type": "pong"}
        layer = get_channel_layer()
        assert layer is not None
        await layer.group_send(
            publication_group(publication.pk),
            {
                "type": "publication.event",
                "event": {
                    "version": 1,
                    "type": "comment.created",
                    "publication_id": str(publication.pk),
                },
            },
        )
        assert (await socket.receive_json_from())["type"] == "comment.created"
        await socket.send_json_to({"type": "comment.create", "body": "forbidden"})
        assert await socket.receive_output() == {"type": "websocket.close", "code": 4400}
        await socket.disconnect()

        malformed = WebsocketCommunicator(
            application,
            f"/ws/v1/publications/{publication.pk}?ticket=valid",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await malformed.connect()
        assert connected
        await malformed.send_to(text_data="not json")
        assert await malformed.receive_output() == {"type": "websocket.close", "code": 4400}
        await malformed.disconnect()

        read_only = WebsocketCommunicator(
            application,
            f"/ws/v1/publications/{publication.pk}?ticket=valid",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await read_only.connect()
        assert connected
        await read_only.send_to(bytes_data=b"no binary")
        assert await read_only.receive_output() == {"type": "websocket.close", "code": 4400}
        await read_only.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_rollback_emits_no_event(settings, monkeypatch):
    _user, publication = make_publication(settings)
    sent = []

    class Layer:
        async def group_send(self, group, event):
            sent.append((group, event))

    monkeypatch.setattr("apps.discussions.events.get_channel_layer", lambda: Layer())
    from apps.discussions.events import publish_after_commit

    with pytest.raises(RuntimeError):
        with transaction.atomic():
            publish_after_commit(
                event_type="comment.created", publication_id=publication.pk, resource_id=None
            )
            raise RuntimeError("rollback")
    assert sent == []
    publish_after_commit(
        event_type="reactions.changed", publication_id=publication.pk, resource_id=None
    )
    assert sent[0][1]["event"]["version"] == 2


@pytest.mark.django_db(transaction=True)
def test_channel_layer_failure_does_not_fail_committed_mutation(settings, monkeypatch):
    _user, publication = make_publication(settings)

    class FailingLayer:
        async def group_send(self, group, event):
            raise RuntimeError("Redis is temporarily unavailable")

    monkeypatch.setattr("apps.discussions.events.get_channel_layer", lambda: FailingLayer())
    from apps.discussions.events import publish_after_commit

    # Django executes the callback immediately outside an atomic block. With a
    # robust callback the already-committed REST mutation remains successful.
    publish_after_commit(
        event_type="comment.created", publication_id=publication.pk, resource_id=None
    )
