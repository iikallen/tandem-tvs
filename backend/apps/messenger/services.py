import unicodedata
from collections.abc import Iterable

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.identity.models import AccessGrant, User

from .events import (
    conversation_created_after_commit,
    message_created_after_commit,
    read_changed_after_commit,
)
from .models import Conversation, ConversationMembership, DirectConversationPair, Message


def normalize_message_body(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "".join(
        character
        for character in normalized
        if character in "\n\t" or unicodedata.category(character) != "Cc"
    ).strip()
    if not normalized:
        raise ValidationError("Message body cannot be blank.")
    if len(normalized) > 10_000:
        raise ValidationError("Message body cannot exceed 10000 characters.")
    return normalized


def eligible_people(user_ids: Iterable[int]):
    return (
        User.objects.filter(
            pk__in=set(user_ids),
            is_active=True,
            access_grants__module=AccessGrant.Module.MESSENGER,
        )
        .select_related("org_unit")
        .distinct()
    )


def member_conversation(user: User, conversation_id: object) -> Conversation:
    return get_object_or_404(
        Conversation.objects.filter(memberships__user=user).distinct(), pk=conversation_id
    )


def create_direct_conversation(creator: User, other: User) -> tuple[Conversation, bool]:
    low_id, high_id = sorted((creator.pk, other.pk))
    existing = (
        DirectConversationPair.objects.select_related("conversation")
        .filter(user_low_id=low_id, user_high_id=high_id)
        .first()
    )
    if existing is not None:
        return existing.conversation, False
    try:
        with transaction.atomic():
            conversation = Conversation.objects.create(
                type=Conversation.Type.DIRECT, created_by=creator
            )
            ConversationMembership.objects.bulk_create(
                [
                    ConversationMembership(conversation=conversation, user_id=low_id),
                    ConversationMembership(conversation=conversation, user_id=high_id),
                ]
            )
            DirectConversationPair.objects.create(
                conversation=conversation, user_low_id=low_id, user_high_id=high_id
            )
            conversation_created_after_commit(conversation.pk, [low_id, high_id])
        return conversation, True
    except IntegrityError:
        pair = DirectConversationPair.objects.select_related("conversation").get(
            user_low_id=low_id, user_high_id=high_id
        )
        return pair.conversation, False


@transaction.atomic
def create_group_conversation(creator: User, *, title: str, members: list[User]) -> Conversation:
    conversation = Conversation.objects.create(
        type=Conversation.Type.GROUP, title=title, created_by=creator
    )
    member_ids = sorted({member.pk for member in members} - {creator.pk})
    ConversationMembership.objects.bulk_create(
        [
            ConversationMembership(
                conversation=conversation,
                user=creator,
                role=ConversationMembership.Role.ADMIN,
            ),
            *[
                ConversationMembership(conversation=conversation, user_id=user_id)
                for user_id in member_ids
            ],
        ]
    )
    conversation_created_after_commit(conversation.pk, [creator.pk, *member_ids])
    return conversation


def send_message(
    conversation: Conversation,
    *,
    author: User,
    client_message_id: object,
    body: str,
) -> tuple[Message, bool]:
    existing = Message.objects.filter(
        conversation=conversation,
        author=author,
        client_message_id=client_message_id,
    ).first()
    if existing is not None:
        return existing, False
    with transaction.atomic():
        locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
        existing = Message.objects.filter(
            conversation=locked,
            author=author,
            client_message_id=client_message_id,
        ).first()
        if existing is not None:
            return existing, False
        now = timezone.now()
        locked.last_sequence += 1
        message = Message.objects.create(
            conversation=locked,
            sequence=locked.last_sequence,
            client_message_id=client_message_id,
            author=author,
            body=body,
        )
        locked.last_message_at = now
        locked.save(update_fields=["last_sequence", "last_message_at", "updated_at"])
        ConversationMembership.objects.filter(conversation=locked, user=author).update(
            last_read_sequence=message.sequence, read_at=now
        )
        message_created_after_commit(locked.pk, message.pk, message.sequence)
        return message, True


@transaction.atomic
def mark_read(conversation: Conversation, *, user: User, sequence: int) -> ConversationMembership:
    locked_conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
    membership = ConversationMembership.objects.select_for_update().get(
        conversation=locked_conversation, user=user
    )
    if sequence > locked_conversation.last_sequence:
        raise ValidationError("Read sequence cannot exceed the conversation sequence.")
    if sequence <= membership.last_read_sequence:
        return membership
    membership.last_read_sequence = sequence
    membership.read_at = timezone.now()
    membership.save(update_fields=["last_read_sequence", "read_at"])
    read_changed_after_commit(locked_conversation.pk, user.pk, sequence)
    return membership
