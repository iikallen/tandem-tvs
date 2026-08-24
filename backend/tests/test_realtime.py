import asyncio
import time
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing.websocket import WebsocketCommunicator
from django.contrib.sessions.backends.db import SessionStore
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.discussions.events import publication_group
from apps.discussions.tickets import TicketClaims, consume_ticket, create_ticket
from apps.identity.models import AccessGrant, User
from apps.publications.models import AudienceRule, Category, Publication
from apps.realtime.claims import RealtimeScope
from apps.realtime.groups import conversation_group, session_control_group, user_control_group
from apps.realtime.middleware import TicketAuthMiddleware
from apps.realtime.security import valid_user_for_ticket
from apps.realtime.session_security import session_fingerprint
from config.asgi import application
from tests.helpers import force_authenticate_portal_fixture


def make_publication(settings):
    client = APIClient()
    force_authenticate_portal_fixture(client, "employee-1")
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


def realtime_session(user: User) -> SessionStore:
    session = SessionStore()
    session["_auth_user_id"] = str(user.pk)
    session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
    session["security_epoch"] = user.security_epoch
    session.save()
    assert session.session_key
    return session


def ticket_claims(
    user: User,
    scope: RealtimeScope,
    resource_id: object | None = None,
) -> TicketClaims:
    session = realtime_session(user)
    assert session.session_key
    return TicketClaims(
        user_id=user.pk,
        security_epoch=user.security_epoch,
        session_key=session.session_key,
        session_fingerprint=session_fingerprint(session.session_key),
        scope=scope,
        resource_id=str(resource_id) if resource_id is not None else None,
    )


@pytest.mark.django_db
def test_messenger_ticket_security_requires_current_epoch_and_grant():
    user = User.objects.create(username="messenger-ticket", full_name="Messenger ticket")
    claims = ticket_claims(user, RealtimeScope.MESSENGER)
    assert valid_user_for_ticket(claims) is None
    AccessGrant.objects.create(user=user, module="MESSENGER", role="MEMBER")
    assert valid_user_for_ticket(claims) == user
    assert valid_user_for_ticket(replace(claims, security_epoch=user.security_epoch + 1)) is None
    assert conversation_group("47d734c6-0f58-4d22-8623-dfe02dc87984") == (
        "conversation.47d734c60f584d228623dfe02dc87984"
    )


@pytest.mark.django_db(transaction=True)
def test_realtime_middleware_routes_messenger_scope_and_rejects_unknown_paths(monkeypatch):
    user = User.objects.create(username="middleware-user", full_name="Middleware user")
    AccessGrant.objects.create(user=user, module="MESSENGER", role="MEMBER")
    claims = ticket_claims(user, RealtimeScope.MESSENGER)
    monkeypatch.setattr(
        "apps.realtime.middleware.consume_ticket",
        lambda token: claims if token == "valid" else None,
    )
    observed = []

    async def inner(scope, _receive, _send):
        observed.append(scope)

    async def receive():
        return {"type": "websocket.disconnect"}

    async def send(_message):
        return None

    middleware = TicketAuthMiddleware(inner)
    unchecked_middleware = cast(Any, middleware)

    async def scenario():
        await unchecked_middleware(
            {"path": "/ws/v1/messenger", "query_string": b"ticket=valid"},
            receive,
            send,
        )
        await unchecked_middleware(
            {"path": "/ws/v1/unknown", "query_string": b"ticket=valid"},
            receive,
            send,
        )

    async_to_sync(scenario)()
    assert observed[0]["user"] == user
    assert observed[0]["realtime_scope"] == RealtimeScope.MESSENGER
    assert observed[1]["ticket_error"] is True


@pytest.mark.django_db
def test_ticket_is_hashed_scoped_and_one_time(settings, monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("apps.realtime.tickets._client", lambda: fake)
    user = User.objects.create(username="ticket-user", full_name="Ticket user")
    session = realtime_session(user)
    token, ttl = create_ticket(
        user_id=user.pk,
        publication_id="publication",
        session_key=cast(str, session.session_key),
    )
    assert ttl == 30
    assert token not in next(iter(fake.values))
    claims = consume_ticket(token)
    assert claims is not None
    assert claims.user_id == user.pk
    assert claims.security_epoch == user.security_epoch
    assert claims.scope == RealtimeScope.NEWS_PUBLICATION
    assert claims.resource_id == "publication"
    assert claims.expires_at > 0
    assert claims.nonce
    assert consume_ticket(token) is None
    assert consume_ticket("") is None
    fake.values["realtime-ticket:bad"] = "not-json"
    monkeypatch.setattr("apps.realtime.tickets._key", lambda token: "realtime-ticket:bad")
    assert consume_ticket("corrupt") is None


@pytest.mark.django_db(transaction=True)
def test_ticket_scope_replay_visibility_lifetime_and_group_cleanup(settings, monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("apps.realtime.tickets._client", lambda: fake)
    user, publication = make_publication(settings)
    session = realtime_session(user)
    session_key = cast(str, session.session_key)
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

    wrong_scope, _ = create_ticket(
        user_id=user.pk, publication_id=publication.pk, session_key=session_key
    )

    async def wrong_publication():
        socket = WebsocketCommunicator(
            application,
            f"/ws/v1/publications/{second.pk}?ticket={wrong_scope}",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, code = await socket.connect()
        assert not connected and code == 4403

    async_to_sync(wrong_publication)()

    one_time, _ = create_ticket(
        user_id=user.pk, publication_id=publication.pk, session_key=session_key
    )

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
    invisible, _ = create_ticket(
        user_id=user.pk, publication_id=publication.pk, session_key=session_key
    )

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
    blocked, _ = create_ticket(
        user_id=user.pk, publication_id=publication.pk, session_key=session_key
    )
    async_to_sync(denied)(blocked)

    user.is_active = True
    user.save(update_fields=["is_active"])
    stale_epoch, _ = create_ticket(
        user_id=user.pk, publication_id=publication.pk, session_key=session_key
    )
    User.objects.filter(pk=user.pk).update(security_epoch=user.security_epoch + 1)
    async_to_sync(denied)(stale_epoch)

    settings.REALTIME_SOCKET_LIFETIME_SECONDS = 0
    user.refresh_from_db()
    session_key = cast(str, realtime_session(user).session_key)
    expiring, _ = create_ticket(
        user_id=user.pk, publication_id=publication.pk, session_key=session_key
    )

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
def test_open_websocket_is_immediately_closed_by_security_invalidation(monkeypatch):
    user, publication = make_publication(None)
    claims = ticket_claims(user, RealtimeScope.NEWS_PUBLICATION, publication.pk)
    monkeypatch.setattr("apps.realtime.middleware.consume_ticket", lambda _token: claims)

    async def scenario():
        socket = WebsocketCommunicator(
            application,
            f"/ws/v1/publications/{publication.pk}?ticket=valid",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await socket.connect()
        assert connected
        layer = get_channel_layer()
        assert layer is not None
        await layer.group_send(
            user_control_group(user.pk),
            {"type": "auth.invalidate"},
        )
        assert await socket.receive_output(timeout=1) == {
            "type": "websocket.close",
            "code": 4403,
        }

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_websocket_origin_ticket_scope_event_and_read_only(settings, monkeypatch):
    user, publication = make_publication(settings)
    claims = ticket_claims(user, RealtimeScope.NEWS_PUBLICATION, publication.pk)
    monkeypatch.setattr(
        "apps.realtime.middleware.consume_ticket",
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

        settings.REALTIME_MAX_CLIENT_FRAMES_PER_SECOND = 2
        flooded = WebsocketCommunicator(
            application,
            f"/ws/v1/publications/{publication.pk}?ticket=valid",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await flooded.connect()
        assert connected
        for _index in range(3):
            await flooded.send_json_to({"type": "ping"})
        assert await flooded.receive_json_from() == {"type": "pong"}
        assert await flooded.receive_json_from() == {"type": "pong"}
        assert await flooded.receive_output() == {"type": "websocket.close", "code": 4429}
        await flooded.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_session_invalidation_closes_only_that_device_and_user_invalidation_closes_all(
    monkeypatch,
):
    user = User.objects.create(username="session-sockets", full_name="Session sockets")
    AccessGrant.objects.create(user=user, module="MESSENGER", role="MEMBER")
    first_claims = ticket_claims(user, RealtimeScope.MESSENGER)
    second_claims = ticket_claims(user, RealtimeScope.MESSENGER)
    monkeypatch.setattr(
        "apps.realtime.middleware.consume_ticket",
        lambda token: {"first": first_claims, "second": second_claims}.get(token),
    )

    async def scenario():
        first = WebsocketCommunicator(
            application,
            "/ws/v1/messenger?ticket=first",
            headers=[(b"origin", b"http://localhost")],
        )
        second = WebsocketCommunicator(
            application,
            "/ws/v1/messenger?ticket=second",
            headers=[(b"origin", b"http://localhost")],
        )
        assert (await first.connect(timeout=3))[0]
        assert (await second.connect(timeout=3))[0]
        layer = get_channel_layer()
        assert layer is not None
        await layer.group_send(
            session_control_group(first_claims.session_fingerprint),
            {"type": "auth.invalidate"},
        )
        assert await first.receive_output(timeout=5) == {
            "type": "websocket.close",
            "code": 4403,
        }
        await second.send_json_to({"type": "ping"})
        assert await second.receive_json_from(timeout=5) == {"type": "pong"}
        await layer.group_send(user_control_group(user.pk), {"type": "auth.invalidate"})
        assert await second.receive_output(timeout=5) == {
            "type": "websocket.close",
            "code": 4403,
        }
        await first.disconnect()
        await second.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_deleted_session_rejects_ticket_and_socket_limit_is_enforced(settings, monkeypatch):
    user = User.objects.create(username="limited-sockets", full_name="Limited sockets")
    AccessGrant.objects.create(user=user, module="MESSENGER", role="MEMBER")
    stale = ticket_claims(user, RealtimeScope.MESSENGER)
    SessionStore(session_key=stale.session_key).delete()
    live = ticket_claims(user, RealtimeScope.MESSENGER)
    settings.REALTIME_MAX_SOCKETS_PER_USER = 2
    settings.REALTIME_MAX_CLIENT_FRAMES_PER_SECOND = 1
    monkeypatch.setattr(
        "apps.realtime.middleware.consume_ticket",
        lambda token: stale if token == "stale" else live,
    )

    async def scenario():
        denied = WebsocketCommunicator(
            application,
            "/ws/v1/messenger?ticket=stale",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, code = await denied.connect(timeout=3)
        assert not connected and code == 4403

        sockets = [
            WebsocketCommunicator(
                application,
                f"/ws/v1/messenger?ticket=live-{index}",
                headers=[(b"origin", b"http://localhost")],
            )
            for index in range(3)
        ]
        assert (await sockets[0].connect(timeout=3))[0]
        assert (await sockets[1].connect(timeout=3))[0]
        connected, code = await sockets[2].connect(timeout=3)
        assert not connected and code == 4429
        await sockets[0].send_json_to({"type": "ping"})
        await sockets[0].send_json_to({"type": "ping"})
        assert await sockets[0].receive_json_from(timeout=5) == {"type": "pong"}
        assert await sockets[0].receive_output(timeout=5) == {
            "type": "websocket.close",
            "code": 4429,
        }
        await sockets[0].disconnect()
        await sockets[1].disconnect()
        await sockets[2].disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_publication_socket_closes_at_its_session_deadline(monkeypatch):
    user, publication = make_publication(None)
    claims = ticket_claims(user, RealtimeScope.NEWS_PUBLICATION, publication.pk)
    monkeypatch.setattr("apps.realtime.middleware.consume_ticket", lambda _token: claims)
    monkeypatch.setattr(
        "apps.realtime.middleware.valid_user_and_session_for_ticket",
        lambda _claims: (user, int(time.time())),
    )
    monkeypatch.setattr("apps.discussions.consumers.ticket_session_deadline", lambda _claims: None)

    async def scenario():
        socket = WebsocketCommunicator(
            application,
            f"/ws/v1/publications/{publication.pk}?ticket=valid",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await socket.connect(timeout=3)
        assert connected
        assert await socket.receive_output(timeout=5) == {
            "type": "websocket.close",
            "code": 4403,
        }
        await socket.disconnect()

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
