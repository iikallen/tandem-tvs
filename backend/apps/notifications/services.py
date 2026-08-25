import logging
from datetime import timedelta
from typing import Any, cast

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.messenger.models import ConversationMembership, Message
from apps.publications.models import PublicationRecipient
from apps.realtime.groups import notification_group
from apps.realtime.outbox import enqueue_realtime_event

from .models import (
    Notification,
    NotificationDelivery,
    NotificationFanoutEvent,
    NotificationPreference,
    NotificationSettings,
)

logger = logging.getLogger(__name__)


def enqueue_fanout(
    *,
    event_key: str,
    event_type: str,
    source_id: object,
    payload: dict[str, object] | None = None,
) -> NotificationFanoutEvent:
    event, _ = NotificationFanoutEvent.objects.get_or_create(
        event_key=event_key,
        defaults={
            "event_type": event_type,
            "source_id": source_id,
            "payload": payload or {},
        },
    )
    return event


def _preferences(user_id: int, event_type: str) -> tuple[bool, bool, bool]:
    settings_row = NotificationSettings.objects.filter(user_id=user_id).first()
    if settings_row is not None and not settings_row.enabled:
        return False, False, False
    preference = NotificationPreference.objects.filter(
        user_id=user_id, notification_type=event_type
    ).first()
    if preference is not None:
        return (
            preference.in_app_enabled,
            preference.push_enabled,
            preference.email_enabled,
        )
    return True, False, event_type == Notification.Type.ACK_REQUIRED


def _dedupe_key(event_type: str, source_id: object, conversation_id: object | None) -> str:
    if event_type == Notification.Type.NEW_MESSAGE:
        return f"conversation:{conversation_id}:messages"
    if event_type == Notification.Type.MESSAGE_MENTION:
        return f"conversation:{conversation_id}:mention"
    return f"{event_type}:{source_id}"


def _delivery_rows(
    notification: Notification,
    *,
    push: bool,
    email: bool,
    external_suppressed: bool,
) -> None:
    if external_suppressed:
        return
    channels = []
    if push and settings.WEB_PUSH_ENABLED:
        channels.append(NotificationDelivery.Channel.PUSH)
    if email and settings.NOTIFICATION_EMAIL_ENABLED:
        channels.append(NotificationDelivery.Channel.EMAIL)
    available_at = (
        timezone.now() + timedelta(seconds=30)
        if notification.notification_type == Notification.Type.NEW_MESSAGE
        else timezone.now()
    )
    NotificationDelivery.objects.bulk_create(
        [
            NotificationDelivery(
                notification=notification,
                channel=channel,
                event_version=notification.event_version,
                available_at=available_at,
            )
            for channel in channels
        ],
        ignore_conflicts=True,
    )


def _bump_unread_group(
    notification: Notification,
    *,
    actor_id: int | None,
    source_id: object,
    payload: dict[str, object] | None,
    in_app: bool,
    occurred_at,
) -> Notification:
    Notification.objects.filter(pk=notification.pk).update(
        actor_id=actor_id,
        source_id=source_id,
        occurrence_count=F("occurrence_count") + 1,
        event_version=F("event_version") + 1,
        last_event_at=occurred_at,
        payload=payload or {},
        in_app_visible=notification.in_app_visible or in_app,
    )
    notification.refresh_from_db()
    return notification


def _upsert_notification(
    *,
    recipient_id: int,
    actor_id: int | None,
    event_type: str,
    source_type: str,
    source_id: object,
    publication_id: object | None = None,
    conversation_id: object | None = None,
    payload: dict[str, object] | None = None,
    external_suppressed: bool = False,
) -> Notification | None:
    in_app, push, email = _preferences(recipient_id, event_type)
    if not any((in_app, push, email)):
        return None
    key = _dedupe_key(event_type, source_id, conversation_id)
    if not in_app:
        key = f"{key}:external"
    existing = (
        Notification.objects.select_for_update()
        .filter(recipient_id=recipient_id, dedupe_key=key, read_at__isnull=True)
        .first()
    )
    now = timezone.now()
    if existing is not None:
        notification = _bump_unread_group(
            existing,
            actor_id=actor_id,
            source_id=source_id,
            payload=payload or {},
            in_app=in_app,
            occurred_at=now,
        )
    else:
        try:
            with transaction.atomic():
                notification = Notification.objects.create(
                    recipient_id=recipient_id,
                    actor_id=actor_id,
                    notification_type=event_type,
                    source_type=source_type,
                    source_id=source_id,
                    publication_id=publication_id,
                    conversation_id=conversation_id,
                    dedupe_key=key,
                    payload=payload or {},
                    in_app_visible=in_app,
                    last_event_at=now,
                )
        except IntegrityError:
            concurrent = Notification.objects.select_for_update().get(
                recipient_id=recipient_id, dedupe_key=key, read_at__isnull=True
            )
            notification = _bump_unread_group(
                concurrent,
                actor_id=actor_id,
                source_id=source_id,
                payload=payload,
                in_app=in_app,
                occurred_at=now,
            )
    _delivery_rows(
        notification,
        push=push,
        email=email,
        external_suppressed=external_suppressed,
    )
    return notification


def _message_recipients(event: NotificationFanoutEvent):
    message = Message.objects.select_related("conversation", "author").get(pk=event.source_id)
    memberships = (
        ConversationMembership.objects.filter(
            conversation=message.conversation,
            user__is_active=True,
            joined_sequence__lt=message.sequence,
        )
        .filter(Q(left_sequence__isnull=True) | Q(left_sequence__gte=message.sequence))
        .select_related("user")
    )
    mentioned = set(cast(Any, message).mentions.values_list("user_id", flat=True))
    for membership in memberships.exclude(user=message.author):
        is_mention = membership.user.pk in mentioned
        event_type = (
            Notification.Type.MESSAGE_MENTION if is_mention else Notification.Type.NEW_MESSAGE
        )
        if membership.notification_mode == ConversationMembership.NotificationMode.NONE:
            continue
        if (
            membership.notification_mode == ConversationMembership.NotificationMode.MENTIONS
            and not is_mention
        ):
            continue
        yield (
            membership.user.pk,
            event_type,
            message.author.pk,
            message.conversation.pk,
            membership.muted_until is not None and membership.muted_until > timezone.now(),
            {"sequence": message.sequence},
        )


def _dispatch(event: NotificationFanoutEvent) -> list[Notification]:
    created: list[Notification] = []
    if event.event_type in {
        Notification.Type.NEW_MESSAGE,
        Notification.Type.MESSAGE_MENTION,
    }:
        for (
            recipient_id,
            event_type,
            actor_id,
            conversation_id,
            muted,
            payload,
        ) in _message_recipients(event):
            row = _upsert_notification(
                recipient_id=recipient_id,
                actor_id=actor_id,
                event_type=event_type,
                source_type="MESSAGE",
                source_id=event.source_id,
                conversation_id=conversation_id,
                payload=payload,
                external_suppressed=muted,
            )
            if row:
                created.append(row)
    elif event.event_type in {
        Notification.Type.NEW_PUBLICATION,
        Notification.Type.ACK_REQUIRED,
    }:
        actor_id = int(event.payload["actor_id"]) if event.payload.get("actor_id") else None
        recipient_ids = event.payload.get("recipient_ids")
        if recipient_ids is None:
            recipient_ids = PublicationRecipient.objects.filter(
                publication_id=event.source_id, is_current=True
            ).values_list("user_id", flat=True)
        for recipient_id in {int(value) for value in recipient_ids}:
            row = _upsert_notification(
                recipient_id=recipient_id,
                actor_id=actor_id,
                event_type=event.event_type,
                source_type="PUBLICATION",
                source_id=event.source_id,
                publication_id=event.source_id,
            )
            if row:
                created.append(row)
    else:
        recipient_ids = {int(value) for value in event.payload.get("recipient_ids", [])}
        actor_id = int(event.payload["actor_id"]) if event.payload.get("actor_id") else None
        publication_id = event.payload.get("publication_id")
        conversation_id = event.payload.get("conversation_id")
        for recipient_id in recipient_ids:
            row = _upsert_notification(
                recipient_id=recipient_id,
                actor_id=actor_id,
                event_type=event.event_type,
                source_type=str(event.payload.get("source_type", event.event_type)),
                source_id=event.source_id,
                publication_id=publication_id,
                conversation_id=conversation_id,
                payload={key: value for key, value in event.payload.items() if key == "sequence"},
            )
            if row:
                created.append(row)
    return created


def process_fanout_event(event_id: object) -> bool:
    try:
        with transaction.atomic():
            event = (
                NotificationFanoutEvent.objects.select_for_update(skip_locked=True)
                .filter(pk=event_id, processed_at__isnull=True, available_at__lte=timezone.now())
                .first()
            )
            if event is None:
                return False
            notifications = _dispatch(event)
            event.attempts += 1
            event.processed_at = timezone.now()
            event.save(update_fields=["attempts", "processed_at"])
            recipient_ids = {cast(Any, row).recipient_id for row in notifications}
            for recipient_id in recipient_ids:
                emit_notification_hint(recipient_id, "notification.changed")
            return True
    except Exception:
        with transaction.atomic():
            failed = NotificationFanoutEvent.objects.select_for_update().get(pk=event_id)
            failed.attempts += 1
            failed.available_at = timezone.now() + timedelta(
                seconds=min(300, 2 ** min(failed.attempts, 8))
            )
            failed.save(update_fields=["attempts", "available_at"])
        logger.exception("notification.fanout.failed", extra={"event_id": str(event_id)})
        return False


def dispatch_pending_fanout(limit: int = 10) -> int:
    ids = list(
        NotificationFanoutEvent.objects.filter(
            processed_at__isnull=True, available_at__lte=timezone.now()
        )
        .order_by("created_at", "id")
        .values_list("pk", flat=True)[:limit]
    )
    return sum(process_fanout_event(event_id) for event_id in ids)


def unread_count(user_id: int) -> int:
    return Notification.objects.filter(
        recipient_id=user_id, in_app_visible=True, read_at__isnull=True
    ).count()


def emit_notification_hint(
    user_id: int, event_type: str, notification_id: object | None = None
) -> None:
    payload: dict[str, object] = {
        "type": event_type,
        "version": 1,
        "unread_count": unread_count(user_id),
    }
    if notification_id is not None:
        payload["notification_id"] = str(notification_id)
    enqueue_realtime_event(notification_group(user_id), event_type.replace(".", "_"), payload)
