from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from apps.notifications.models import (
    NotificationDelivery,
    NotificationFanoutEvent,
    PushSubscription,
)
from apps.realtime.models import RealtimeOutboxEvent

CLEANUP_BATCH_SIZE = 500


def _delete_in_batches(queryset) -> int:
    deleted = 0
    while primary_keys := list(
        queryset.order_by("pk").values_list("pk", flat=True)[:CLEANUP_BATCH_SIZE]
    ):
        with transaction.atomic():
            batch_size, _ = queryset.filter(pk__in=primary_keys).delete()
        deleted += min(batch_size, len(primary_keys))
    return deleted


@shared_task(name="ops.cleanup-operational-data")
def cleanup_operational_data() -> dict[str, int]:
    now = timezone.now()
    realtime_cutoff = now - timedelta(days=settings.OPS_REALTIME_OUTBOX_RETENTION_DAYS)
    notification_cutoff = now - timedelta(days=settings.OPS_NOTIFICATION_OUTBOX_RETENTION_DAYS)
    delivery_cutoff = now - timedelta(days=settings.OPS_NOTIFICATION_DELIVERY_RETENTION_DAYS)
    push_cutoff = now - timedelta(days=settings.OPS_DISABLED_PUSH_RETENTION_DAYS)

    querysets = {
        "expired_sessions": Session.objects.filter(expire_date__lt=now),
        "realtime_outbox": RealtimeOutboxEvent.objects.filter(delivered_at__lt=realtime_cutoff),
        "notification_fanout": NotificationFanoutEvent.objects.filter(
            processed_at__lt=notification_cutoff
        ),
        "notification_deliveries": NotificationDelivery.objects.filter(
            status__in={
                NotificationDelivery.Status.SENT,
                NotificationDelivery.Status.DISABLED,
                NotificationDelivery.Status.FAILED,
            },
            created_at__lt=delivery_cutoff,
        ),
        "disabled_push_subscriptions": PushSubscription.objects.filter(
            enabled=False,
            updated_at__lt=push_cutoff,
        ),
    }
    return {name: _delete_in_batches(queryset) for name, queryset in querysets.items()}
