import importlib
import threading
import time
import uuid
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
import redis
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing.websocket import WebsocketCommunicator
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import close_old_connections, connection, transaction
from django.test import override_settings
from django.utils import timezone
from pywebpush import WebPushException
from rest_framework.test import APIClient

from apps.discussions.models import Comment
from apps.discussions.services import create_comment, delete_comment
from apps.identity.models import AccessGrant, User
from apps.messenger.models import (
    ConversationMembership,
    MessageMention,
)
from apps.messenger.services import create_direct_conversation, delete_message, send_message
from apps.notifications.consumers import NotificationConsumer
from apps.notifications.delivery import _external_allowed, deliver, dispatch_pending_deliveries
from apps.notifications.models import (
    Notification,
    NotificationDelivery,
    NotificationFanoutEvent,
    NotificationPreference,
    NotificationSettings,
    PushSubscription,
)
from apps.notifications.push import send_wakeup
from apps.notifications.services import (
    _upsert_notification,
    dispatch_pending_fanout,
    enqueue_fanout,
    process_fanout_event,
)
from apps.publications.models import (
    AudienceRule,
    Category,
    MediaAsset,
    MediaUsage,
    Publication,
    PublicationRecipient,
)
from apps.publications.services import transition_publication
from apps.realtime.claims import RealtimeScope, RealtimeTicket
from apps.realtime.groups import notification_group, user_control_group
from apps.realtime.outbox import _deliver_inline_if_available


def account(
    username: str,
    *,
    messenger_role: str | None = AccessGrant.Role.MEMBER,
    news_role: str | None = None,
    email: str = "",
) -> User:
    user = User.objects.create(
        username=username,
        full_name=username.replace("-", " ").title(),
        email=email,
    )
    if messenger_role:
        AccessGrant.objects.create(
            user=user, module=AccessGrant.Module.MESSENGER, role=messenger_role
        )
    if news_role:
        AccessGrant.objects.create(user=user, module=AccessGrant.Module.NEWS, role=news_role)
    return user


def client(user: User) -> APIClient:
    api = APIClient()
    api.force_authenticate(user)
    return api


def publication(
    author: User,
    slug: str,
    *,
    title: str = "Маяк для сотрудников",
    recipient: User | None = None,
    acknowledgement_required: bool = False,
) -> Publication:
    category, _ = Category.objects.get_or_create(slug="stage9", defaults={"name": "Stage 9"})
    row = Publication.objects.create(
        title=title,
        slug=slug,
        summary=title,
        body={
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": title}]}],
        },
        category=category,
        author=author,
        acknowledgement_required=acknowledgement_required,
    )
    AudienceRule.objects.create(
        publication=row,
        kind=AudienceRule.Kind.EMPLOYEE if recipient else AudienceRule.Kind.ALL,
        employee=recipient,
    )
    return row


def test_legacy_notification_migration_preserves_identity_and_read_state():
    migration = importlib.import_module(
        "apps.notifications.migrations.0002_migrate_legacy_notifications"
    )
    notification_id = uuid.uuid4()
    publication_id = uuid.uuid4()
    comment_id = uuid.uuid4()
    created_at = timezone.now() - timedelta(days=1)
    read_at = timezone.now()
    legacy = SimpleNamespace(
        id=notification_id,
        recipient_id=7,
        actor_id=8,
        notification_type=Notification.Type.COMMENT_REPLY,
        publication_id=publication_id,
        comment_id=comment_id,
        created_at=created_at,
        read_at=read_at,
    )
    captured = []

    class LegacyRows:
        def all(self):
            return self

        def iterator(self, *, chunk_size):
            assert chunk_size == 500
            return iter([legacy])

    class LegacyModel:
        objects = LegacyRows()

    class UnifiedRows:
        def bulk_create(self, rows):
            for row in rows:
                row.created_at = timezone.now()
                row.last_event_at = row.created_at
            captured.extend(rows)

        def bulk_update(self, rows, fields):
            assert fields == ["created_at", "last_event_at", "read_at"]

    class UnifiedModel:
        objects = UnifiedRows()

        def __init__(self, **kwargs):
            vars(self).update(kwargs)

    class HistoricalApps:
        @staticmethod
        def get_model(app_label, model_name):
            return (
                LegacyModel
                if (app_label, model_name) == ("discussions", "Notification")
                else UnifiedModel
            )

    migration.migrate_legacy(HistoricalApps(), None)
    assert len(captured) == 1
    copied = captured[0]
    assert copied.id == notification_id
    assert copied.recipient_id == 7 and copied.actor_id == 8
    assert copied.source_id == comment_id and copied.publication_id == publication_id
    assert copied.created_at == created_at and copied.read_at == read_at


def test_realtime_inline_delivery_skips_unavailable_redis(monkeypatch):
    class RedisLayer:
        __module__ = "channels_redis.fake"

    class Unavailable:
        def ping(self):
            raise redis.ConnectionError("offline")

    delivered = []
    monkeypatch.setattr("apps.realtime.outbox.get_channel_layer", RedisLayer)
    monkeypatch.setattr(
        "apps.realtime.outbox.redis.Redis.from_url", lambda *_a, **_k: Unavailable()
    )
    monkeypatch.setattr("apps.realtime.outbox.deliver_outbox_event", delivered.append)
    _deliver_inline_if_available("offline-event")
    assert delivered == []

    class Available:
        @staticmethod
        def ping():
            return True

    monkeypatch.setattr("apps.realtime.outbox.redis.Redis.from_url", lambda *_a, **_k: Available())
    _deliver_inline_if_available("online-event")
    assert delivered == ["online-event"]


@pytest.mark.django_db
def test_channel_writer_discussion_mentions_all_and_exact_context(settings):
    admin = account("channel-admin", messenger_role=AccessGrant.Role.ADMIN)
    writer = account("channel-writer")
    member = account("channel-member")
    outsider = account("channel-outsider")
    response = client(admin).post(
        "/api/v1/messenger/conversations/channel",
        {
            "title": "Announcements",
            "member_ids": [writer.pk, member.pk],
            "writer_ids": [writer.pk],
            "discussion_enabled": True,
        },
        format="json",
    )
    assert response.status_code == 201
    conversation_id = response.data["id"]
    assert response.data["type"] == "CHANNEL"
    dispatch_pending_fanout()
    assert Notification.objects.filter(
        recipient=member,
        notification_type=Notification.Type.CHAT_ADDED,
        conversation_id=conversation_id,
    ).exists()
    assert (
        ConversationMembership.objects.get(conversation_id=conversation_id, user=writer).role
        == ConversationMembership.Role.WRITER
    )
    url = f"/api/v1/messenger/conversations/{conversation_id}/messages"
    denied = client(member).post(
        url,
        {
            "client_message_id": str(uuid.uuid4()),
            "body": "member post",
            "kind": "CHANNEL_POST",
        },
        format="json",
    )
    assert denied.status_code == 403
    discussion = client(member).post(
        url,
        {
            "client_message_id": str(uuid.uuid4()),
            "body": "discussion",
            "kind": "DISCUSSION",
            "mentioned_user_ids": [writer.pk],
        },
        format="json",
    )
    assert discussion.status_code == 201
    assert MessageMention.objects.filter(message_id=discussion.data["id"], user=writer).exists()
    channel_post = client(writer).post(
        url,
        {
            "client_message_id": str(uuid.uuid4()),
            "body": "announcement",
            "kind": "CHANNEL_POST",
            "mention_all": True,
        },
        format="json",
    )
    assert channel_post.status_code == 201
    assert MessageMention.objects.filter(message_id=channel_post.data["id"]).count() == 2
    assert client(outsider).get(url).status_code == 404
    context = client(member).get(f"{url}/{discussion.data['id']}/context")
    assert context.status_code == 200
    assert context.data["target"]["id"] == discussion.data["id"]

    disabled = client(admin).patch(
        f"/api/v1/messenger/conversations/{conversation_id}",
        {"discussion_enabled": False},
        format="json",
    )
    assert disabled.status_code == 200
    assert disabled.data["discussion_enabled"] is False
    assert (
        client(member)
        .patch(
            f"/api/v1/messenger/conversations/{conversation_id}",
            {"discussion_enabled": True},
            format="json",
        )
        .status_code
        == 403
    )
    blocked_discussion = client(member).post(
        url,
        {
            "client_message_id": str(uuid.uuid4()),
            "body": "discussion disabled",
            "kind": "DISCUSSION",
        },
        format="json",
    )
    assert blocked_discussion.status_code == 403

    direct, _ = create_direct_conversation(admin, member)
    direct_response = client(admin).post(
        f"/api/v1/messenger/conversations/{direct.pk}/messages",
        {
            "client_message_id": str(uuid.uuid4()),
            "body": "all",
            "mention_all": True,
        },
        format="json",
    )
    assert direct_response.status_code == 400


@pytest.mark.django_db
def test_channel_mention_all_is_rate_limited():
    cache.clear()
    admin = account("throttle-admin", messenger_role=AccessGrant.Role.ADMIN)
    member = account("throttle-member")
    created = client(admin).post(
        "/api/v1/messenger/conversations/channel",
        {
            "title": "Rate limited channel",
            "member_ids": [member.pk],
            "writer_ids": [],
        },
        format="json",
    )
    url = f"/api/v1/messenger/conversations/{created.data['id']}/messages"
    statuses = [
        client(admin)
        .post(
            url,
            {
                "client_message_id": str(uuid.uuid4()),
                "body": f"announcement {index}",
                "kind": "CHANNEL_POST",
                "mention_all": "true",
            },
            format="json",
        )
        .status_code
        for index in range(11)
    ]
    assert statuses[:10] == [201] * 10
    assert statuses[10] == 429


@pytest.mark.django_db
def test_messenger_stage9_validation_edges():
    admin = account("validation-admin", messenger_role=AccessGrant.Role.ADMIN)
    member = account("validation-member")
    api = client(admin)

    duplicate_writer = api.post(
        "/api/v1/messenger/conversations/channel",
        {
            "title": "Invalid writers",
            "member_ids": [member.pk],
            "writer_ids": [member.pk, member.pk],
        },
        format="json",
    )
    assert duplicate_writer.status_code == 400
    non_member_writer = api.post(
        "/api/v1/messenger/conversations/channel",
        {
            "title": "Invalid membership",
            "member_ids": [member.pk],
            "writer_ids": [admin.pk],
        },
        format="json",
    )
    assert non_member_writer.status_code == 400

    direct, _ = create_direct_conversation(admin, member)
    messages_url = f"/api/v1/messenger/conversations/{direct.pk}/messages"
    assert (
        api.patch(
            f"/api/v1/messenger/conversations/{direct.pk}",
            {"discussion_enabled": True},
            format="json",
        ).status_code
        == 400
    )
    invalid_payloads = [
        {"body": "message", "unexpected": True},
        {"body": "\x00"},
        {"body": "message", "attachment_ids": [str(uuid.uuid4())] * 2},
        {"body": "message", "mentioned_user_ids": [member.pk, member.pk]},
        {"body": "message", "mentioned_user_ids": [member.pk], "mention_all": True},
    ]
    for payload in invalid_payloads:
        payload["client_message_id"] = str(uuid.uuid4())
        assert api.post(messages_url, payload, format="json").status_code == 400
    assert (
        api.post(
            messages_url,
            {
                "client_message_id": str(uuid.uuid4()),
                "body": "wrong kind",
                "kind": "CHANNEL_POST",
            },
            format="json",
        ).status_code
        == 400
    )
    attachment_id = uuid.uuid4()
    with pytest.raises(DjangoValidationError, match="Attachments must be unique"):
        send_message(
            direct,
            author=admin,
            client_message_id=uuid.uuid4(),
            body="duplicate attachment",
            attachment_ids=[attachment_id, attachment_id],
        )
    with pytest.raises(DjangoValidationError, match="requires text"):
        send_message(
            direct,
            author=admin,
            client_message_id=uuid.uuid4(),
            body="",
        )
    outsider = account("validation-outsider")
    with pytest.raises(DjangoValidationError, match="active conversation member"):
        send_message(
            direct,
            author=admin,
            client_message_id=uuid.uuid4(),
            body="invalid mention",
            mentioned_user_ids=[outsider.pk],
        )

    channel = api.post(
        "/api/v1/messenger/conversations/channel",
        {"title": "Validation channel", "member_ids": [member.pk]},
        format="json",
    )
    assert channel.status_code == 201
    assert (
        api.post(
            f"/api/v1/messenger/conversations/{channel.data['id']}/messages",
            {"client_message_id": str(uuid.uuid4()), "body": "wrong kind", "kind": "CHAT"},
            format="json",
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_messenger_search_filters_attachment_and_interval_authorization():
    owner = account("search-owner")
    peer = account("search-peer")
    outsider = account("search-outsider")
    conversation, _ = create_direct_conversation(owner, peer)
    asset = MediaAsset.objects.create(
        original_name="contract.pdf",
        storage_key="stage9/contract.pdf",
        file="stage9/contract.pdf",
        mime_type="application/pdf",
        size=10,
        sha256="9" * 64,
        kind=MediaAsset.Kind.DOCUMENT,
        uploader=owner,
    )
    first, _ = send_message(
        conversation,
        author=owner,
        client_message_id=uuid.uuid4(),
        body="Поисковая новость",
        attachment_ids=[asset.pk],
    )
    send_message(
        conversation,
        author=peer,
        client_message_id=uuid.uuid4(),
        body="other",
    )
    base = f"/api/v1/messenger/conversations/{conversation.pk}/search"
    empty_search = client(owner).get(base)
    assert empty_search.status_code == 400, empty_search.data
    assert client(outsider).get(f"{base}?q=новость").status_code == 404
    by_author = client(owner).get(f"{base}?author_id={owner.pk}")
    assert [row["id"] for row in by_author.data["results"]] == [str(first.pk)]
    attached = client(owner).get(f"{base}?has_attachments=true")
    assert [row["id"] for row in attached.data["results"]] == [str(first.pk)]
    date_from = (first.created_at - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    date_to = (first.created_at + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    dated = client(owner).get(f"{base}?date_from={date_from}&date_to={date_to}")
    assert str(first.pk) in {row["id"] for row in dated.data["results"]}
    assert client(owner).get(f"{base}?date_from={date_to}&date_to={date_from}").status_code == 400


@pytest.mark.django_db
def test_message_fanout_grouping_mentions_preferences_read_and_retry(monkeypatch):
    author = account("fanout-author")
    recipient = account("fanout-recipient")
    conversation, _ = create_direct_conversation(author, recipient)
    first, _ = send_message(
        conversation,
        author=author,
        client_message_id=uuid.uuid4(),
        body="one",
    )
    second, _ = send_message(
        conversation,
        author=author,
        client_message_id=uuid.uuid4(),
        body="two",
    )
    assert Notification.objects.count() == 0
    assert dispatch_pending_fanout() == 2
    grouped = Notification.objects.get(
        recipient=recipient, notification_type=Notification.Type.NEW_MESSAGE
    )
    assert grouped.occurrence_count == 2
    assert grouped.source_id == second.pk
    assert dispatch_pending_fanout() == 0

    assert client(recipient).post(f"/api/v1/notifications/{grouped.pk}/read").status_code == 204
    after_read, _ = send_message(
        conversation,
        author=author,
        client_message_id=uuid.uuid4(),
        body="new unread group",
    )
    dispatch_pending_fanout()
    new_group = Notification.objects.get(
        recipient=recipient,
        notification_type=Notification.Type.NEW_MESSAGE,
        source_id=after_read.pk,
    )
    assert new_group.occurrence_count == 1
    assert (
        Notification.objects.filter(
            recipient=recipient, notification_type=Notification.Type.NEW_MESSAGE
        ).count()
        == 2
    )
    mentioned, _ = send_message(
        conversation,
        author=author,
        client_message_id=uuid.uuid4(),
        body="mention",
        mentioned_user_ids=[recipient.pk],
    )
    dispatch_pending_fanout()
    mention = Notification.objects.get(
        recipient=recipient,
        notification_type=Notification.Type.MESSAGE_MENTION,
        source_id=mentioned.pk,
    )
    assert mention.occurrence_count == 1
    assert (
        Notification.objects.filter(
            recipient=recipient,
            notification_type=Notification.Type.NEW_MESSAGE,
            source_id=mentioned.pk,
        ).count()
        == 0
    )

    membership = ConversationMembership.objects.get(conversation=conversation, user=recipient)
    membership.notification_mode = ConversationMembership.NotificationMode.NONE
    membership.save(update_fields=["notification_mode"])
    send_message(
        conversation,
        author=author,
        client_message_id=uuid.uuid4(),
        body="suppressed",
    )
    dispatch_pending_fanout()
    assert Notification.objects.filter(recipient=recipient).count() == 3

    event = enqueue_fanout(
        event_key="retry-stage9",
        event_type=Notification.Type.CHAT_ADDED,
        source_id=conversation.pk,
        payload={
            "recipient_ids": [recipient.pk],
            "conversation_id": str(conversation.pk),
        },
    )
    original = __import__("apps.notifications.services", fromlist=["_dispatch"])._dispatch
    monkeypatch.setattr("apps.notifications.services._dispatch", lambda _event: 1 / 0)
    assert process_fanout_event(event.pk) is False
    event.refresh_from_db()
    assert event.attempts == 1 and event.processed_at is None
    NotificationFanoutEvent.objects.filter(pk=event.pk).update(available_at=timezone.now())
    monkeypatch.setattr("apps.notifications.services._dispatch", original)
    assert process_fanout_event(event.pk) is True


@pytest.mark.django_db(transaction=True)
def test_concurrent_unread_group_insert_keeps_both_occurrences(monkeypatch):
    recipient = account("concurrent-group-recipient")
    barrier = threading.Barrier(2)
    original_create = Notification.objects.create

    def synchronized_create(*args, **kwargs):
        barrier.wait(timeout=10)
        return original_create(*args, **kwargs)

    monkeypatch.setattr(Notification.objects, "create", synchronized_create)
    errors = []

    def worker(source_id):
        close_old_connections()
        try:
            with transaction.atomic():
                _upsert_notification(
                    recipient_id=recipient.pk,
                    actor_id=None,
                    event_type=Notification.Type.NEW_MESSAGE,
                    source_type="MESSAGE",
                    source_id=source_id,
                    conversation_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
                )
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(uuid.uuid4(),)) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    grouped = Notification.objects.get(recipient=recipient)
    assert grouped.occurrence_count == 2
    assert grouped.event_version == 2


@pytest.mark.django_db
@override_settings(WEB_PUSH_ENABLED=True)
def test_external_delivery_rechecks_current_chat_suppression():
    author = account("delivery-policy-author")
    recipient = account("delivery-policy-recipient")
    conversation, _ = create_direct_conversation(author, recipient)
    membership = ConversationMembership.objects.get(conversation=conversation, user=recipient)
    NotificationPreference.objects.create(
        user=recipient,
        notification_type=Notification.Type.NEW_MESSAGE,
        push_enabled=True,
    )
    notification = Notification.objects.create(
        recipient=recipient,
        notification_type=Notification.Type.NEW_MESSAGE,
        source_type="MESSAGE",
        source_id=uuid.uuid4(),
        conversation_id=conversation.pk,
        dedupe_key="delivery-policy",
    )

    membership.notification_mode = ConversationMembership.NotificationMode.NONE
    membership.save(update_fields=["notification_mode"])
    assert not _external_allowed(notification, NotificationDelivery.Channel.PUSH)

    membership.notification_mode = ConversationMembership.NotificationMode.MENTIONS
    membership.save(update_fields=["notification_mode"])
    assert not _external_allowed(notification, NotificationDelivery.Channel.PUSH)

    membership.notification_mode = ConversationMembership.NotificationMode.ALL
    membership.muted_until = timezone.now() + timedelta(hours=1)
    membership.save(update_fields=["notification_mode", "muted_until"])
    assert not _external_allowed(notification, NotificationDelivery.Channel.PUSH)

    membership.muted_until = None
    membership.save(update_fields=["muted_until"])
    assert _external_allowed(notification, NotificationDelivery.Channel.PUSH)

    membership.left_at = timezone.now()
    membership.left_sequence = conversation.last_sequence
    membership.save(update_fields=["left_at", "left_sequence"])
    assert not _external_allowed(notification, NotificationDelivery.Channel.PUSH)


@pytest.mark.django_db
@override_settings(WEB_PUSH_ENABLED=True)
def test_chat_modes_mute_and_external_only_delivery():
    author = account("preference-author")
    recipient = account("preference-recipient")
    conversation, _ = create_direct_conversation(author, recipient)
    membership = ConversationMembership.objects.get(conversation=conversation, user=recipient)
    membership.notification_mode = ConversationMembership.NotificationMode.MENTIONS
    membership.save(update_fields=["notification_mode"])
    NotificationPreference.objects.create(
        user=recipient,
        notification_type=Notification.Type.NEW_MESSAGE,
        in_app_enabled=False,
        push_enabled=True,
    )

    send_message(
        conversation,
        author=author,
        client_message_id=uuid.uuid4(),
        body="ordinary",
    )
    dispatch_pending_fanout()
    assert not Notification.objects.filter(recipient=recipient).exists()

    NotificationPreference.objects.create(
        user=recipient,
        notification_type=Notification.Type.MESSAGE_MENTION,
        in_app_enabled=False,
        push_enabled=True,
    )
    mentioned, _ = send_message(
        conversation,
        author=author,
        client_message_id=uuid.uuid4(),
        body="external only",
        mentioned_user_ids=[recipient.pk],
    )
    dispatch_pending_fanout()
    hidden = Notification.objects.get(recipient=recipient, source_id=mentioned.pk)
    assert hidden.in_app_visible is False
    assert NotificationDelivery.objects.filter(
        notification=hidden, channel=NotificationDelivery.Channel.PUSH
    ).exists()
    assert client(recipient).get("/api/v1/notifications").data["results"] == []
    assert client(recipient).get("/api/v1/notifications/unread-count").data == {"unread_count": 0}

    NotificationPreference.objects.filter(
        user=recipient, notification_type=Notification.Type.MESSAGE_MENTION
    ).update(in_app_enabled=True)
    membership.muted_until = timezone.now() + timedelta(hours=1)
    membership.save(update_fields=["muted_until"])
    muted, _ = send_message(
        conversation,
        author=author,
        client_message_id=uuid.uuid4(),
        body="muted external channel",
        mentioned_user_ids=[recipient.pk],
    )
    dispatch_pending_fanout()
    hidden.refresh_from_db()
    assert hidden.source_id == mentioned.pk and hidden.in_app_visible is False
    assert NotificationDelivery.objects.filter(notification=hidden).count() == 1
    visible = Notification.objects.get(recipient=recipient, source_id=muted.pk)
    assert visible.in_app_visible is True
    assert not NotificationDelivery.objects.filter(notification=visible).exists()


@pytest.mark.django_db
def test_notification_api_settings_cross_user_and_realtime_ticket(monkeypatch):
    owner = account("notification-owner", messenger_role=None)
    other = account("notification-other", messenger_role=None)
    row = Notification.objects.create(
        recipient=owner,
        notification_type=Notification.Type.NEW_PUBLICATION,
        source_type="PUBLICATION",
        source_id=uuid.uuid4(),
        dedupe_key="api-test",
    )
    inbox = client(owner).get("/api/v1/notifications")
    assert inbox.status_code == 200 and inbox.data["results"][0]["id"] == str(row.pk)
    assert client(other).post(f"/api/v1/notifications/{row.pk}/read").status_code == 404
    patched = client(owner).patch(
        "/api/v1/notification-settings",
        {
            "enabled": True,
            "preferences": [
                {
                    "notification_type": "NEW_MESSAGE",
                    "in_app_enabled": False,
                    "push_enabled": False,
                    "email_enabled": False,
                }
            ],
        },
        format="json",
    )
    assert patched.status_code == 200
    assert NotificationPreference.objects.get(user=owner).in_app_enabled is False
    monkeypatch.setattr(
        "apps.discussions.views.create_realtime_ticket", lambda **_kwargs: ("ticket", 30)
    )
    ticket = client(owner).post(
        "/api/v1/realtime/tickets", {"scope": "NOTIFICATIONS"}, format="json"
    )
    assert ticket.status_code == 200 and ticket.data["ticket"] == "ticket"
    assert client(owner).post("/api/v1/notifications/read-all").data["updated"] == 1


@pytest.mark.django_db(transaction=True)
def test_notification_realtime_reaches_two_devices():
    recipient = account("realtime-notification-user", messenger_role=None)
    claims = RealtimeTicket(
        user_id=recipient.pk,
        security_epoch=recipient.security_epoch,
        session_key="test-session",
        session_fingerprint="test-fingerprint",
        scope=RealtimeScope.NOTIFICATIONS,
        expires_at=int(time.time()) + 60,
        nonce="test-nonce",
    )
    consumer = NotificationConsumer.as_asgi()

    async def authenticated_consumer(scope, receive, send):
        scope.update(
            user=recipient,
            session_fingerprint=claims.session_fingerprint,
            session_deadline=int(time.time()) + 60,
            realtime_claims=claims,
        )
        await consumer(scope, receive, send)

    async def scenario():
        first = WebsocketCommunicator(authenticated_consumer, "/ws/v1/notifications")
        second = WebsocketCommunicator(authenticated_consumer, "/ws/v1/notifications")
        assert (await first.connect())[0]
        assert (await second.connect())[0]
        layer = get_channel_layer()
        assert layer is not None
        event = {"type": "notification.changed", "unread_count": 4}
        await layer.group_send(
            notification_group(recipient.pk),
            {"type": "notification.changed", "event": event},
        )
        assert await first.receive_json_from() == event
        assert await second.receive_json_from() == event
        await first.disconnect()
        await second.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_notification_socket_limit_is_enforced_and_lease_is_released(settings, monkeypatch):
    recipient = account("realtime-notification-limit", messenger_role=None)
    claims = RealtimeTicket(
        user_id=recipient.pk,
        security_epoch=recipient.security_epoch,
        session_key="test-session",
        session_fingerprint="test-fingerprint",
        scope=RealtimeScope.NOTIFICATIONS,
        expires_at=int(time.time()) + 60,
        nonce="test-nonce",
    )
    settings.REALTIME_MAX_SOCKETS_PER_USER = 1
    active: set[str] = set()
    released: list[str] = []

    def reserve(_user_id, connection_id):
        if len(active) >= settings.REALTIME_MAX_SOCKETS_PER_USER:
            return False
        active.add(connection_id)
        return True

    def release(_user_id, connection_id):
        active.discard(connection_id)
        released.append(connection_id)

    monkeypatch.setattr("apps.notifications.consumers.reserve_socket", reserve)
    monkeypatch.setattr("apps.notifications.consumers.release_socket", release)
    consumer = NotificationConsumer.as_asgi()

    async def authenticated(scope, receive, send):
        scope.update(
            user=recipient,
            session_fingerprint=claims.session_fingerprint,
            session_deadline=int(time.time()) + 60,
            realtime_claims=claims,
        )
        await consumer(scope, receive, send)

    async def scenario():
        first = WebsocketCommunicator(authenticated, "/ws/v1/notifications")
        denied = WebsocketCommunicator(authenticated, "/ws/v1/notifications")
        assert (await first.connect())[0]
        assert await denied.connect() == (False, 4429)
        await first.disconnect()
        assert len(released) == 1 and not active

        replacement = WebsocketCommunicator(authenticated, "/ws/v1/notifications")
        assert (await replacement.connect())[0]
        await replacement.disconnect()
        await denied.disconnect()
        assert len(released) == 2 and not active

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_notification_realtime_rejects_bad_clients_and_auth_invalidation(settings):
    recipient = account("realtime-notification-controls", messenger_role=None)
    claims = RealtimeTicket(
        user_id=recipient.pk,
        security_epoch=recipient.security_epoch,
        session_key="test-session",
        session_fingerprint="test-fingerprint",
        scope=RealtimeScope.NOTIFICATIONS,
        expires_at=int(time.time()) + 60,
        nonce="test-nonce",
    )
    consumer = NotificationConsumer.as_asgi()

    async def authenticated(scope, receive, send):
        scope.update(
            user=recipient,
            session_fingerprint=claims.session_fingerprint,
            session_deadline=int(time.time()) + 60,
            realtime_claims=claims,
        )
        await consumer(scope, receive, send)

    async def scenario():
        rejected = WebsocketCommunicator(consumer, "/ws/v1/notifications")
        assert await rejected.connect() == (False, 4403)

        ping = WebsocketCommunicator(authenticated, "/ws/v1/notifications")
        assert (await ping.connect())[0]
        await ping.send_json_to({"type": "ping"})
        assert await ping.receive_json_from() == {"type": "pong"}
        await ping.send_json_to({"type": "unsupported"})
        assert await ping.receive_output() == {"type": "websocket.close", "code": 4400}

        binary = WebsocketCommunicator(authenticated, "/ws/v1/notifications")
        assert (await binary.connect())[0]
        await binary.send_to(bytes_data=b"not allowed")
        assert await binary.receive_output() == {"type": "websocket.close", "code": 4400}

        invalidated = WebsocketCommunicator(authenticated, "/ws/v1/notifications")
        assert (await invalidated.connect())[0]
        layer = get_channel_layer()
        assert layer is not None
        await layer.group_send(
            user_control_group(recipient.pk),
            {"type": "auth.invalidate"},
        )
        assert await invalidated.receive_output() == {
            "type": "websocket.close",
            "code": 4403,
        }
        await invalidated.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db
@override_settings(
    WEB_PUSH_ENABLED=True,
    VAPID_PUBLIC_KEY="public",
    WEB_PUSH_ALLOWED_HOST_SUFFIXES=("example.invalid",),
    WEB_PUSH_MAX_SUBSCRIPTIONS_PER_USER=1,
)
def test_push_subscription_is_owned_redacted_and_expired_cleanup(monkeypatch):
    owner = account("push-owner")
    other = account("push-other")
    payload = {
        "endpoint": "https://push.example.invalid/secret-endpoint",
        "p256dh": "p256dh-secret",
        "auth": "auth-secret",
    }
    assert (
        client(owner).post("/api/v1/push/subscriptions", payload, format="json").status_code == 204
    )
    subscription = PushSubscription.objects.get(user=owner)
    assert "secret-endpoint" not in str(subscription)
    assert (
        client(owner)
        .post(
            "/api/v1/push/subscriptions",
            {**payload, "endpoint": "https://push.example.invalid/second"},
            format="json",
        )
        .status_code
        == 400
    )
    assert (
        client(owner)
        .post(
            "/api/v1/push/subscriptions",
            {**payload, "endpoint": "https://127.0.0.1/private"},
            format="json",
        )
        .status_code
        == 400
    )
    assert (
        client(other).post("/api/v1/push/subscriptions", payload, format="json").status_code == 400
    )
    response = SimpleNamespace(status_code=410)
    monkeypatch.setattr(
        "apps.notifications.push.webpush",
        lambda **_kwargs: (_ for _ in ()).throw(WebPushException("gone", response=response)),
    )
    assert send_wakeup(subscription) == "expired"
    subscription.refresh_from_db()
    assert subscription.enabled is False
    subscription.enabled = True
    subscription.save(update_fields=["enabled", "updated_at"])
    monkeypatch.setattr("apps.notifications.push.webpush", lambda **_kwargs: None)
    assert send_wakeup(subscription) == "sent"
    server_error = SimpleNamespace(status_code=500)
    monkeypatch.setattr(
        "apps.notifications.push.webpush",
        lambda **_kwargs: (_ for _ in ()).throw(WebPushException("failed", response=server_error)),
    )
    with pytest.raises(WebPushException):
        send_wakeup(subscription)


@pytest.mark.django_db
@override_settings(NOTIFICATION_EMAIL_ENABLED=True)
def test_smtp_failure_does_not_remove_source_or_notification(monkeypatch):
    recipient = account("smtp-recipient", email="smtp@example.test")
    notification = Notification.objects.create(
        recipient=recipient,
        notification_type=Notification.Type.ACK_REQUIRED,
        source_type="PUBLICATION",
        source_id=uuid.uuid4(),
        dedupe_key="smtp-test",
    )
    delivery_row = NotificationDelivery.objects.create(
        notification=notification,
        channel=NotificationDelivery.Channel.EMAIL,
        event_version=1,
    )
    monkeypatch.setattr(
        "apps.notifications.delivery.send_mail",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError("smtp down")),
    )
    assert deliver(delivery_row.pk) is False
    delivery_row.refresh_from_db()
    assert delivery_row.attempts == 1
    assert Notification.objects.filter(pk=notification.pk).exists()


@pytest.mark.django_db
@override_settings(NOTIFICATION_EMAIL_ENABLED=True, WEB_PUSH_ENABLED=True)
def test_delivery_outcomes_queue_and_task_wrappers(monkeypatch):
    recipient = account("delivery-recipient", email="delivery@example.test")
    NotificationPreference.objects.create(
        user=recipient,
        notification_type=Notification.Type.NEW_MESSAGE,
        push_enabled=True,
        email_enabled=True,
    )
    NotificationPreference.objects.create(
        user=recipient,
        notification_type=Notification.Type.NEW_PUBLICATION,
        email_enabled=True,
    )

    def notification(key: str, kind=Notification.Type.NEW_MESSAGE):
        return Notification.objects.create(
            recipient=recipient,
            notification_type=kind,
            source_type="MESSAGE",
            source_id=uuid.uuid4(),
            dedupe_key=key,
        )

    active = notification("delivery-active")
    recipient.last_activity_at = timezone.now()
    recipient.save(update_fields=["last_activity_at"])
    active_delivery = NotificationDelivery.objects.create(
        notification=active,
        channel=NotificationDelivery.Channel.EMAIL,
        event_version=1,
    )
    assert deliver(active_delivery.pk) is False
    active_delivery.refresh_from_db()
    assert active_delivery.status == NotificationDelivery.Status.PENDING

    important = notification("delivery-important", Notification.Type.ACK_REQUIRED)
    important_delivery = NotificationDelivery.objects.create(
        notification=important,
        channel=NotificationDelivery.Channel.EMAIL,
        event_version=1,
    )
    monkeypatch.setattr("apps.notifications.delivery.send_mail", lambda *_args, **_kwargs: 1)
    assert deliver(important_delivery.pk) is True

    no_push = notification("delivery-no-push")
    no_push_delivery = NotificationDelivery.objects.create(
        notification=no_push,
        channel=NotificationDelivery.Channel.PUSH,
        event_version=1,
    )
    assert deliver(no_push_delivery.pk) is False
    no_push_delivery.refresh_from_db()
    assert no_push_delivery.error_code == "no_subscription"

    grouped = notification("delivery-superseded")
    older = NotificationDelivery.objects.create(
        notification=grouped,
        channel=NotificationDelivery.Channel.PUSH,
        event_version=1,
    )
    NotificationDelivery.objects.create(
        notification=grouped,
        channel=NotificationDelivery.Channel.PUSH,
        event_version=2,
        available_at=timezone.now() + timedelta(days=1),
    )
    assert deliver(older.pk) is False
    older.refresh_from_db()
    assert older.status == NotificationDelivery.Status.DISABLED
    assert older.error_code == "superseded"

    recipient.last_activity_at = None
    recipient.save(update_fields=["last_activity_at"])
    queued = notification("delivery-queued", Notification.Type.NEW_PUBLICATION)
    NotificationDelivery.objects.create(
        notification=queued,
        channel=NotificationDelivery.Channel.EMAIL,
        event_version=1,
    )
    assert dispatch_pending_deliveries() == 1

    disabled = notification("delivery-disabled", Notification.Type.ACK_REQUIRED)
    disabled_delivery = NotificationDelivery.objects.create(
        notification=disabled,
        channel=NotificationDelivery.Channel.EMAIL,
        event_version=1,
    )
    NotificationSettings.objects.create(user=recipient, enabled=False)
    assert deliver(disabled_delivery.pk) is False
    disabled_delivery.refresh_from_db()
    assert disabled_delivery.error_code == "preference_disabled"

    monkeypatch.setattr("apps.notifications.tasks.dispatch_pending_fanout", lambda: 7)
    monkeypatch.setattr("apps.notifications.tasks.dispatch_pending_deliveries", lambda: 8)
    from apps.notifications.tasks import (
        dispatch_notification_deliveries,
        dispatch_notification_fanout,
    )

    assert cast(Any, dispatch_notification_fanout).run() == 7
    assert cast(Any, dispatch_notification_deliveries).run() == 8


@pytest.mark.django_db
def test_notification_disabled_settings_and_push_validation():
    recipient = account("disabled-notifications")
    author = account("disabled-notification-author")
    conversation, _ = create_direct_conversation(author, recipient)
    NotificationSettings.objects.create(user=recipient, enabled=False)
    send_message(
        conversation,
        author=author,
        client_message_id=uuid.uuid4(),
        body="fully disabled",
    )
    dispatch_pending_fanout()
    assert not Notification.objects.filter(recipient=recipient).exists()

    api = client(recipient)
    assert api.get("/api/v1/push/config").data == {
        "enabled": False,
        "vapid_public_key": "",
    }
    assert (
        api.post(
            "/api/v1/push/subscriptions",
            {
                "endpoint": "https://push.example.invalid/subscription",
                "p256dh": "secret",
                "auth": "secret",
            },
            format="json",
        ).status_code
        == 400
    )
    duplicate = api.patch(
        "/api/v1/notification-settings",
        {
            "preferences": [
                {
                    "notification_type": "NEW_MESSAGE",
                    "in_app_enabled": True,
                    "push_enabled": False,
                    "email_enabled": False,
                },
                {
                    "notification_type": "NEW_MESSAGE",
                    "in_app_enabled": True,
                    "push_enabled": False,
                    "email_enabled": False,
                },
            ]
        },
        format="json",
    )
    assert duplicate.status_code == 400


@pytest.mark.django_db
def test_publication_comment_and_ack_fanout_are_durable():
    editor = account("notify-editor", news_role=AccessGrant.Role.EDITOR)
    recipient = account("notify-recipient")
    mentioned = account("notify-mentioned")
    row = publication(
        editor,
        "notify-publication",
        recipient=recipient,
        acknowledgement_required=True,
    )
    AudienceRule.objects.create(
        publication=row, kind=AudienceRule.Kind.EMPLOYEE, employee=mentioned
    )
    transition_publication(row, action="publish", actor=editor)
    assert NotificationFanoutEvent.objects.filter(source_id=row.pk).count() == 2
    PublicationRecipient.objects.filter(publication=row).update(is_current=False)
    dispatch_pending_fanout()
    assert set(
        Notification.objects.filter(recipient=recipient).values_list("notification_type", flat=True)
    ) == {Notification.Type.NEW_PUBLICATION, Notification.Type.ACK_REQUIRED}

    root = create_comment(publication=row, author=recipient, body="root")
    reply = create_comment(
        publication=row,
        author=editor,
        body="reply",
        reply_to_id=root.pk,
        mentioned_users=[mentioned],
    )
    dispatch_pending_fanout()
    assert Notification.objects.filter(
        recipient=recipient,
        source_id=reply.pk,
        notification_type=Notification.Type.COMMENT_REPLY,
    ).exists()
    assert Notification.objects.filter(
        recipient=mentioned,
        source_id=reply.pk,
        notification_type=Notification.Type.COMMENT_MENTION,
    ).exists()


@pytest.mark.django_db
def test_global_search_has_five_sections_morphology_and_no_idor():
    editor = account("search-editor", news_role=AccessGrant.Role.EDITOR)
    viewer = account("search-viewer", news_role=None)
    other = account("search-private-user")
    viewer.full_name = "Маяк Сотрудник"
    viewer.job_title = "Аналитик"
    viewer.save(update_fields=["full_name", "job_title"])

    visible = publication(editor, "search-visible", title="Маяк новость адамға", recipient=viewer)
    transition_publication(visible, action="publish", actor=editor)
    comment = create_comment(publication=visible, author=editor, body="Маяк комментарий")
    asset = MediaAsset.objects.create(
        original_name="маяк-документ.pdf",
        storage_key="stage9/mayak.pdf",
        file="stage9/mayak.pdf",
        mime_type="application/pdf",
        size=10,
        sha256="8" * 64,
        kind=MediaAsset.Kind.DOCUMENT,
        uploader=editor,
    )
    MediaUsage.objects.create(
        asset=asset, publication=visible, purpose=MediaUsage.Purpose.ATTACHMENT
    )
    conversation, _ = create_direct_conversation(editor, viewer)
    message, _ = send_message(
        conversation,
        author=editor,
        client_message_id=uuid.uuid4(),
        body="Маяк сообщение",
    )

    hidden = publication(editor, "search-hidden", title="Тайна новость", recipient=other)
    transition_publication(hidden, action="publish", actor=editor)
    hidden_comment = create_comment(publication=hidden, author=editor, body="Тайна комментарий")
    hidden_comment.status = Comment.Status.HIDDEN
    hidden_comment.save(update_fields=["status"])
    private_conversation, _ = create_direct_conversation(editor, other)
    send_message(
        private_conversation,
        author=editor,
        client_message_id=uuid.uuid4(),
        body="Тайна сообщение",
    )
    hidden_asset = MediaAsset.objects.create(
        original_name="тайна-файл.pdf",
        storage_key="stage9/private.pdf",
        file="stage9/private.pdf",
        mime_type="application/pdf",
        size=10,
        sha256="7" * 64,
        kind=MediaAsset.Kind.DOCUMENT,
        uploader=editor,
    )
    MediaUsage.objects.create(
        asset=hidden_asset, publication=hidden, purpose=MediaUsage.Purpose.ATTACHMENT
    )
    MediaAsset.objects.create(
        original_name="тайна-сирота.pdf",
        storage_key="stage9/orphan.pdf",
        file="stage9/orphan.pdf",
        mime_type="application/pdf",
        size=10,
        sha256="6" * 64,
        kind=MediaAsset.Kind.DOCUMENT,
        uploader=editor,
    )
    inactive = account("search-inactive")
    inactive.full_name = "Тайна Сотрудник"
    inactive.is_active = False
    inactive.save(update_fields=["full_name", "is_active"])

    deleted_comment = create_comment(publication=visible, author=editor, body="Исчезнувшая заметка")
    delete_comment(publication=visible, comment_id=deleted_comment.pk, actor=editor)
    deleted_message, _ = send_message(
        conversation,
        author=editor,
        client_message_id=uuid.uuid4(),
        body="Исчезнувшее сообщение",
    )
    delete_message(deleted_message, actor=editor)

    response = client(viewer).get("/api/v1/search?q=маяк")
    assert response.status_code == 200
    assert all(response.data[section] for section in response.data)
    assert response.data["messages"][0]["url"].endswith(f"message={message.pk}")
    assert response.data["comments"][0]["id"] == str(comment.pk)
    leaked = client(viewer).get("/api/v1/search?q=тайна")
    assert all(not rows for rows in leaked.data.values())
    deleted = client(viewer).get("/api/v1/search?q=исчезнувшая")
    assert all(not rows for rows in deleted.data.values())
    russian = client(viewer).get("/api/v1/search?q=новостями&scope=publications")
    assert any(row["id"] == str(visible.pk) for row in russian.data["results"])
    kazakh = client(viewer).get("/api/v1/search?q=адам&scope=publications")
    assert any(row["id"] == str(visible.pk) for row in kazakh.data["results"])
    assert (
        client(viewer).get("/api/v1/search?q=маяк&scope=publications&cursor=a").status_code == 400
    )
    assert client(other).get("/api/v1/search?q=маяк&cursor=bad&scope=messages").status_code == 400
