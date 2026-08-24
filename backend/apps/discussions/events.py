import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

from apps.realtime.groups import publication_group


def publish_after_commit(
    *, event_type: str, publication_id: object, resource_id: object | None
) -> None:
    event = {
        "version": 2,
        "event_id": str(uuid.uuid4()),
        "type": event_type,
        "publication_id": str(publication_id),
        "resource_id": str(resource_id) if resource_id is not None else None,
        "occurred_at": timezone.now().isoformat(),
    }

    def send() -> None:
        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)(
                publication_group(publication_id),
                {"type": "publication.event", "event": event},
            )

    # The database mutation is already durable at this point. A transient
    # channel-layer outage must not turn a successful REST mutation into a 500
    # that clients may retry and duplicate.
    transaction.on_commit(send, robust=True)
