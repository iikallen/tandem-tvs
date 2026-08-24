import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

from apps.realtime.groups import conversation_group, user_control_group


def _hint(event_type: str, conversation_id: object, **identifiers: object) -> dict[str, object]:
    return {
        "version": 1,
        "event_id": str(uuid.uuid4()),
        "type": event_type,
        "conversation_id": str(conversation_id),
        **identifiers,
        "occurred_at": timezone.now().isoformat(),
    }


def _send(group: str, event: dict[str, object]) -> None:
    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(group, {"type": event["type"], "event": event})


def conversation_created_after_commit(conversation_id: object, user_ids: list[int]) -> None:
    event = _hint("messenger.conversation.created", conversation_id)

    def send() -> None:
        for user_id in user_ids:
            _send(user_control_group(user_id), event)

    transaction.on_commit(send, robust=True)


def message_created_after_commit(
    conversation_id: object, message_id: object, sequence: int
) -> None:
    event = _hint(
        "messenger.message.created",
        conversation_id,
        message_id=str(message_id),
        sequence=sequence,
    )
    transaction.on_commit(lambda: _send(conversation_group(conversation_id), event), robust=True)


def read_changed_after_commit(conversation_id: object, user_id: int, sequence: int) -> None:
    event = _hint("messenger.read.changed", conversation_id, user_id=user_id, sequence=sequence)
    transaction.on_commit(lambda: _send(conversation_group(conversation_id), event), robust=True)


def membership_changed_after_commit(event_type: str, conversation_id: object, user_id: int) -> None:
    event = _hint(event_type, conversation_id, user_id=user_id)
    transaction.on_commit(lambda: _send(user_control_group(user_id), event), robust=True)
