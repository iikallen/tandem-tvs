from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import connection, transaction
from django.utils import timezone

from apps.notifications.models import (
    NotificationDelivery,
    NotificationFanoutEvent,
    PushSubscription,
)
from apps.publications.models import MediaAsset
from apps.realtime.models import RealtimeOutboxEvent

from .metrics import BACKUP_WRITE_LOCK_ID

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


def _delete_temporary_media(queryset) -> int:
    deleted = 0
    while assets := list(queryset.order_by("pk")[:CLEANUP_BATCH_SIZE]):
        with transaction.atomic():
            for asset in assets:
                storage = asset.file.storage
                name = asset.file.name
                asset.delete()
                transaction.on_commit(lambda s=storage, n=name: s.delete(n), robust=True)
        deleted += len(assets)
    return deleted


@shared_task(name="ops.cleanup-operational-data")
def cleanup_operational_data() -> dict[str, int]:
    backup_lock = False
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock_shared(%s)", [BACKUP_WRITE_LOCK_ID])
            backup_lock = bool(cursor.fetchone()[0])
        if not backup_lock:
            return {
                "expired_sessions": 0,
                "realtime_outbox": 0,
                "notification_fanout": 0,
                "notification_deliveries": 0,
                "disabled_push_subscriptions": 0,
                "temporary_uploads": 0,
            }

    try:
        return _cleanup_operational_data()
    finally:
        if backup_lock:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock_shared(%s)", [BACKUP_WRITE_LOCK_ID])


def _cleanup_operational_data() -> dict[str, int]:
    now = timezone.now()
    realtime_cutoff = now - timedelta(days=settings.OPS_REALTIME_OUTBOX_RETENTION_DAYS)
    notification_cutoff = now - timedelta(days=settings.OPS_NOTIFICATION_OUTBOX_RETENTION_DAYS)
    delivery_cutoff = now - timedelta(days=settings.OPS_NOTIFICATION_DELIVERY_RETENTION_DAYS)
    push_cutoff = now - timedelta(days=settings.OPS_DISABLED_PUSH_RETENTION_DAYS)

    temporary_uploads = MediaAsset.objects.filter(
        temporary_until__lt=now,
        usages__isnull=True,
        cover_publications__isnull=True,
        comment_attachments__isnull=True,
        messenger_attachments__isnull=True,
    )

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
    deleted = {name: _delete_in_batches(queryset) for name, queryset in querysets.items()}
    deleted["temporary_uploads"] = _delete_temporary_media(temporary_uploads)
    return deleted
