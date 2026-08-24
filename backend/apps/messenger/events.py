from django.utils import timezone

from apps.realtime.groups import conversation_group, user_control_group
from apps.realtime.outbox import enqueue_realtime_event


def _hint(event_type: str, conversation_id: object, **identifiers: object) -> dict[str, object]:
    return {
        "version": 2,
        "type": event_type,
        "conversation_id": str(conversation_id),
        **identifiers,
        "occurred_at": timezone.now().isoformat(),
    }


def conversation_created_after_commit(conversation_id: object, user_ids: list[int]) -> None:
    event = _hint("messenger.conversation.created", conversation_id)
    for user_id in user_ids:
        enqueue_realtime_event(user_control_group(user_id), str(event["type"]), event)


def message_created_after_commit(
    conversation_id: object, message_id: object, sequence: int
) -> None:
    event = _hint(
        "messenger.message.created",
        conversation_id,
        message_id=str(message_id),
        sequence=sequence,
    )
    enqueue_realtime_event(conversation_group(conversation_id), str(event["type"]), event)


def read_changed_after_commit(
    conversation_id: object,
    user_id: int,
    sequence: int,
    *,
    event_type: str = "messenger.read.changed",
) -> None:
    event = _hint(event_type, conversation_id, user_id=user_id, sequence=sequence)
    enqueue_realtime_event(conversation_group(conversation_id), str(event["type"]), event)


def membership_changed_after_commit(event_type: str, conversation_id: object, user_id: int) -> None:
    event = _hint(event_type, conversation_id, user_id=user_id)
    if event_type == "messenger.membership.added":
        enqueue_realtime_event(user_control_group(user_id), str(event["type"]), event)
    enqueue_realtime_event(conversation_group(conversation_id), str(event["type"]), event)


def message_changed_after_commit(
    event_type: str,
    conversation_id: object,
    message_id: object,
    sequence: int,
) -> None:
    event = _hint(
        event_type,
        conversation_id,
        message_id=str(message_id),
        sequence=sequence,
    )
    enqueue_realtime_event(conversation_group(conversation_id), str(event["type"]), event)


def conversation_changed_after_commit(event_type: str, conversation_id: object) -> None:
    event = _hint(event_type, conversation_id)
    enqueue_realtime_event(conversation_group(conversation_id), str(event["type"]), event)


def user_conversation_changed_after_commit(
    event_type: str, conversation_id: object, user_id: int
) -> None:
    event = _hint(event_type, conversation_id, user_id=user_id)
    enqueue_realtime_event(user_control_group(user_id), str(event["type"]), event)
