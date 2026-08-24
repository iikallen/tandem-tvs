import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

from .models import RealtimeOutboxEvent

logger = logging.getLogger(__name__)


def enqueue_realtime_event(
    group_name: str,
    event_type: str,
    payload: dict[str, object],
) -> RealtimeOutboxEvent:
    row = RealtimeOutboxEvent.objects.create(
        group_name=group_name,
        event_type=event_type,
        payload={**payload},
    )
    row.payload["event_id"] = str(row.pk)
    row.save(update_fields=["payload"])
    transaction.on_commit(lambda: deliver_outbox_event(row.pk), robust=True)
    return row


def deliver_outbox_event(event_id: object) -> bool:
    with transaction.atomic():
        event = (
            RealtimeOutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(pk=event_id, delivered_at__isnull=True, available_at__lte=timezone.now())
            .first()
        )
        if event is None:
            return False
        event.attempts += 1
        try:
            layer = get_channel_layer()
            if layer is None:
                raise RuntimeError("Realtime channel layer is unavailable.")
            async_to_sync(layer.group_send)(
                event.group_name,
                {"type": event.event_type, "event": event.payload},
            )
        except Exception:
            delay = min(60, 2 ** min(event.attempts, 5))
            event.available_at = timezone.now() + timedelta(seconds=delay)
            event.save(update_fields=["attempts", "available_at"])
            logger.exception(
                "realtime.outbox.delivery_failed",
                extra={"event_id": str(event.pk), "event_type": event.event_type},
            )
            return False
        event.delivered_at = timezone.now()
        event.save(update_fields=["attempts", "delivered_at"])
        return True


def dispatch_pending_outbox(limit: int = 100) -> int:
    ids = list(
        RealtimeOutboxEvent.objects.filter(
            delivered_at__isnull=True,
            available_at__lte=timezone.now(),
        )
        .order_by("created_at", "id")
        .values_list("pk", flat=True)[:limit]
    )
    return sum(deliver_outbox_event(event_id) for event_id in ids)
