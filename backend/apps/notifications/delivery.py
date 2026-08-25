import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.messenger.models import ConversationMembership

from .models import Notification, NotificationDelivery, PushSubscription
from .push import send_wakeup
from .services import _preferences

logger = logging.getLogger(__name__)


def _external_allowed(notification: Notification, channel: str) -> bool:
    _in_app, push, email = _preferences(notification.recipient.pk, notification.notification_type)
    if channel == NotificationDelivery.Channel.PUSH and not (push and settings.WEB_PUSH_ENABLED):
        return False
    if channel == NotificationDelivery.Channel.EMAIL and not (
        email and settings.NOTIFICATION_EMAIL_ENABLED
    ):
        return False
    if notification.conversation_id and notification.notification_type in {
        Notification.Type.NEW_MESSAGE,
        Notification.Type.MESSAGE_MENTION,
        Notification.Type.CHAT_ADDED,
    }:
        membership = ConversationMembership.objects.filter(
            conversation_id=notification.conversation_id,
            user=notification.recipient,
            left_at__isnull=True,
        ).first()
        if membership is None:
            return False
        if membership.notification_mode == ConversationMembership.NotificationMode.NONE:
            return False
        if (
            membership.notification_mode == ConversationMembership.NotificationMode.MENTIONS
            and notification.notification_type == Notification.Type.NEW_MESSAGE
        ):
            return False
        if membership.muted_until is not None and membership.muted_until > timezone.now():
            return False
    return True


def _send_email(notification: Notification) -> str:
    user = notification.recipient
    if not user.email:
        return "no_address"
    if notification.notification_type not in {
        Notification.Type.ACK_REQUIRED,
        Notification.Type.NEW_PUBLICATION,
    }:
        inactive_after = timezone.now() - timedelta(
            hours=settings.NOTIFICATION_EMAIL_INACTIVE_AFTER_HOURS
        )
        if user.last_activity_at is not None and user.last_activity_at > inactive_after:
            return "active"
    private = notification.notification_type in {
        Notification.Type.NEW_MESSAGE,
        Notification.Type.MESSAGE_MENTION,
        Notification.Type.CHAT_ADDED,
    }
    body = (
        "You have new messages in Tandem Portal."
        if private
        else "You have an important notification in Tandem Portal."
    )
    send_mail("Tandem Portal notification", body, settings.DEFAULT_FROM_EMAIL, [user.email])
    return "sent"


def _send_push(notification: Notification) -> str:
    subscriptions = PushSubscription.objects.filter(user=notification.recipient, enabled=True)
    if not subscriptions.exists():
        return "no_subscription"
    outcomes = [send_wakeup(subscription) for subscription in subscriptions]
    return "sent" if "sent" in outcomes else "expired"


def deliver(delivery_id: int) -> bool:
    try:
        with transaction.atomic():
            row = (
                NotificationDelivery.objects.select_for_update(skip_locked=True)
                .select_related("notification__recipient")
                .filter(
                    pk=delivery_id,
                    status=NotificationDelivery.Status.PENDING,
                    available_at__lte=timezone.now(),
                )
                .first()
            )
            if row is None:
                return False
            newer = NotificationDelivery.objects.filter(
                notification=row.notification,
                channel=row.channel,
                event_version__gt=row.event_version,
            ).exists()
            if newer:
                row.status = NotificationDelivery.Status.DISABLED
                row.error_code = "superseded"
            else:
                row.attempts += 1
                if not _external_allowed(row.notification, row.channel):
                    outcome = "preference_disabled"
                else:
                    outcome = (
                        _send_push(row.notification)
                        if row.channel == NotificationDelivery.Channel.PUSH
                        else _send_email(row.notification)
                    )
                if outcome == "active":
                    row.available_at = timezone.now() + timedelta(minutes=15)
                    row.save(update_fields=["attempts", "available_at"])
                    return False
                row.status = (
                    NotificationDelivery.Status.SENT
                    if outcome == "sent"
                    else NotificationDelivery.Status.DISABLED
                )
                row.error_code = "" if outcome == "sent" else outcome
                row.sent_at = timezone.now() if outcome == "sent" else None
            row.save(update_fields=["status", "attempts", "sent_at", "error_code", "available_at"])
            return row.status == NotificationDelivery.Status.SENT
    except Exception as exc:
        with transaction.atomic():
            row = NotificationDelivery.objects.select_for_update().get(pk=delivery_id)
            row.attempts += 1
            row.error_code = type(exc).__name__[:64]
            row.available_at = timezone.now() + timedelta(
                seconds=min(900, 2 ** min(row.attempts, 9))
            )
            if row.attempts >= 8:
                row.status = NotificationDelivery.Status.FAILED
            row.save(update_fields=["attempts", "error_code", "available_at", "status"])
        logger.exception(
            "notification.delivery.failed",
            extra={"delivery_id": delivery_id, "channel": row.channel},
        )
        return False


def dispatch_pending_deliveries(limit: int = 100) -> int:
    ids = list(
        NotificationDelivery.objects.filter(
            status=NotificationDelivery.Status.PENDING,
            available_at__lte=timezone.now(),
        )
        .order_by("created_at", "id")
        .values_list("pk", flat=True)[:limit]
    )
    return sum(deliver(delivery_id) for delivery_id in ids)
