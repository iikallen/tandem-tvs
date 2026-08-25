import hashlib
import json
import unicodedata
from collections.abc import Iterable

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied

from apps.identity.models import AccessGrant, User
from apps.publications.models import AuditEvent, MediaAsset
from apps.publications.services import record_audit_event

from .events import (
    conversation_changed_after_commit,
    conversation_created_after_commit,
    membership_changed_after_commit,
    message_changed_after_commit,
    message_created_after_commit,
    read_changed_after_commit,
    user_conversation_changed_after_commit,
)
from .models import (
    Conversation,
    ConversationMembership,
    DirectConversationPair,
    Message,
    MessageAttachment,
    MessageMention,
    MessageReaction,
    MessageRevision,
    PinnedMessage,
)


class IdempotencyConflict(APIException):
    status_code = 422
    default_code = "idempotency_conflict"
    default_detail = "client_message_id was already used with another payload."


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


def message_request_fingerprint(
    *,
    body: str,
    reply_to_id: object | None = None,
    attachment_ids: Iterable[object] = (),
    forward_message_id: object | None = None,
    kind: str = Message.Kind.CHAT,
    mentioned_user_ids: Iterable[int] = (),
    mention_all: bool = False,
) -> str:
    canonical = json.dumps(
        {
            "attachment_ids": [str(value) for value in attachment_ids],
            "body": body,
            "forward_message_id": str(forward_message_id) if forward_message_id else None,
            "kind": kind,
            "mention_all": mention_all,
            "mentioned_user_ids": sorted(set(mentioned_user_ids)),
            "reply_to_id": str(reply_to_id) if reply_to_id else None,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _same_request(message: Message, fingerprint: str) -> None:
    if message.request_fingerprint != fingerprint:
        raise IdempotencyConflict()


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
        Conversation.objects.filter(
            memberships__user=user,
            memberships__left_at__isnull=True,
        ).distinct(),
        pk=conversation_id,
    )


def active_membership(
    conversation: Conversation,
    user: User,
    *,
    for_update: bool = False,
) -> ConversationMembership:
    queryset = ConversationMembership.objects.filter(
        conversation=conversation,
        user=user,
        left_at__isnull=True,
    )
    if for_update:
        queryset = queryset.select_for_update()
    return get_object_or_404(queryset)


def membership_message_filter(user: User, conversation: Conversation) -> Q:
    intervals = list(
        ConversationMembership.objects.filter(conversation=conversation, user=user).values_list(
            "joined_sequence", "left_sequence"
        )
    )
    if not intervals:
        return Q(pk__in=[])
    visible = Q()
    for joined, left in intervals:
        window = Q(sequence__gt=joined)
        if left is not None:
            window &= Q(sequence__lte=left)
        visible |= window
    return visible


def visible_message(user: User, message_id: object) -> Message:
    message = get_object_or_404(
        Message.objects.select_related("conversation", "author"), pk=message_id
    )
    is_active = ConversationMembership.objects.filter(
        conversation=message.conversation,
        user=user,
        left_at__isnull=True,
    ).exists()
    is_visible = Message.objects.filter(
        membership_message_filter(user, message.conversation), pk=message.pk
    ).exists()
    if not is_active or not is_visible:
        from django.http import Http404

        raise Http404
    return message


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
                type=Conversation.Type.DIRECT, created_by=creator, activity_at=timezone.now()
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
        type=Conversation.Type.GROUP,
        title=title,
        created_by=creator,
        activity_at=timezone.now(),
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
    if member_ids:
        from apps.notifications.models import Notification
        from apps.notifications.services import enqueue_fanout

        enqueue_fanout(
            event_key=f"conversation:{conversation.pk}:created",
            event_type=Notification.Type.CHAT_ADDED,
            source_id=conversation.pk,
            payload={
                "actor_id": creator.pk,
                "conversation_id": str(conversation.pk),
                "recipient_ids": member_ids,
                "source_type": "CONVERSATION",
            },
        )
    return conversation


@transaction.atomic
def create_channel(
    creator: User,
    *,
    title: str,
    members: list[User],
    writer_ids: set[int],
    discussion_enabled: bool,
) -> Conversation:
    conversation = Conversation.objects.create(
        type=Conversation.Type.CHANNEL,
        title=title,
        created_by=creator,
        discussion_enabled=discussion_enabled,
        activity_at=timezone.now(),
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
                ConversationMembership(
                    conversation=conversation,
                    user_id=user_id,
                    role=(
                        ConversationMembership.Role.WRITER
                        if user_id in writer_ids
                        else ConversationMembership.Role.MEMBER
                    ),
                )
                for user_id in member_ids
            ],
        ]
    )
    conversation_created_after_commit(conversation.pk, [creator.pk, *member_ids])
    if member_ids:
        from apps.notifications.models import Notification
        from apps.notifications.services import enqueue_fanout

        enqueue_fanout(
            event_key=f"conversation:{conversation.pk}:created",
            event_type=Notification.Type.CHAT_ADDED,
            source_id=conversation.pk,
            payload={
                "actor_id": creator.pk,
                "conversation_id": str(conversation.pk),
                "recipient_ids": member_ids,
                "source_type": "CONVERSATION",
            },
        )
    return conversation


def require_message_permission(
    *,
    conversation: Conversation,
    membership: ConversationMembership,
    kind: str,
) -> None:
    if conversation.type in {Conversation.Type.DIRECT, Conversation.Type.GROUP}:
        if kind != Message.Kind.CHAT:
            raise ValidationError("Direct and group chats accept CHAT messages only.")
        return
    if conversation.type != Conversation.Type.CHANNEL:
        raise ValidationError("Unknown conversation type.")
    if kind == Message.Kind.CHANNEL_POST:
        if membership.role not in {
            ConversationMembership.Role.WRITER,
            ConversationMembership.Role.ADMIN,
        }:
            raise PermissionDenied("Only channel writers may publish posts.")
        return
    if kind == Message.Kind.DISCUSSION:
        if not conversation.discussion_enabled:
            raise PermissionDenied("Channel discussion is disabled.")
        return
    raise ValidationError("Channels do not accept regular chat messages.")


@transaction.atomic
def update_channel_settings(
    conversation: Conversation,
    *,
    actor: User,
    discussion_enabled: bool,
) -> Conversation:
    locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
    membership = active_membership(locked, actor, for_update=True)
    if locked.type != Conversation.Type.CHANNEL:
        raise ValidationError("Only channels have discussion settings.")
    if membership.role != ConversationMembership.Role.ADMIN:
        raise PermissionDenied("A channel administrator is required.")
    if locked.discussion_enabled != discussion_enabled:
        locked.discussion_enabled = discussion_enabled
        locked.save(update_fields=["discussion_enabled", "updated_at"])
        conversation_changed_after_commit("messenger.conversation.updated", locked.pk)
    return locked


def resolve_message_mentions(
    *,
    conversation: Conversation,
    mentioned_user_ids: set[int],
    mention_all: bool,
) -> list[User]:
    if mention_all and conversation.type == Conversation.Type.DIRECT:
        raise ValidationError("@all is not allowed in direct conversations.")
    if not mention_all and not mentioned_user_ids:
        return []
    eligible = User.objects.filter(
        conversation_memberships__conversation=conversation,
        conversation_memberships__left_at__isnull=True,
        is_active=True,
    ).distinct()
    if mention_all:
        return list(eligible)
    resolved = list(eligible.filter(pk__in=mentioned_user_ids))
    if len(resolved) != len(mentioned_user_ids):
        raise ValidationError("Every mentioned user must be an active conversation member.")
    return resolved


def send_message(
    conversation: Conversation,
    *,
    author: User,
    client_message_id: object,
    body: str,
    reply_to_id: object | None = None,
    attachment_ids: Iterable[object] = (),
    forward_message_id: object | None = None,
    kind: str = Message.Kind.CHAT,
    mentioned_user_ids: Iterable[int] = (),
    mention_all: bool = False,
) -> tuple[Message, bool]:
    attachment_ids = tuple(attachment_ids)
    mentioned_user_ids = tuple(mentioned_user_ids)
    if len(attachment_ids) != len(set(attachment_ids)):
        raise ValidationError("Attachments must be unique.")
    if body:
        body = normalize_message_body(body)
    if not body and forward_message_id is None and not attachment_ids:
        raise ValidationError("A message requires text, a forward, or an attachment.")
    fingerprint = message_request_fingerprint(
        body=body,
        reply_to_id=reply_to_id,
        attachment_ids=attachment_ids,
        forward_message_id=forward_message_id,
        kind=kind,
        mentioned_user_ids=mentioned_user_ids,
        mention_all=mention_all,
    )
    existing = Message.objects.filter(
        conversation=conversation,
        author=author,
        client_message_id=client_message_id,
    ).first()
    if existing is not None:
        _same_request(existing, fingerprint)
        return existing, False
    with transaction.atomic():
        locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
        membership = active_membership(locked, author, for_update=True)
        require_message_permission(
            conversation=locked,
            membership=membership,
            kind=kind,
        )
        existing = Message.objects.filter(
            conversation=locked,
            author=author,
            client_message_id=client_message_id,
        ).first()
        if existing is not None:
            _same_request(existing, fingerprint)
            return existing, False
        reply_to = None
        if reply_to_id is not None:
            reply_to = get_object_or_404(
                Message.objects.filter(
                    membership_message_filter(author, locked),
                    conversation=locked,
                    deleted_at__isnull=True,
                ),
                pk=reply_to_id,
            )
        forwarded_snapshot = None
        if forward_message_id is not None:
            source = visible_message(author, forward_message_id)
            if source.deleted_at is not None:
                raise PermissionDenied("Deleted messages cannot be forwarded.")
            forwarded_snapshot = {
                "author_name": source.author.full_name,
                "body": source.body,
                "created_at": source.created_at.isoformat(),
            }
        assets_by_id = {
            asset.pk: asset
            for asset in MediaAsset.objects.filter(
                pk__in=attachment_ids,
                uploader=author,
                status=MediaAsset.Status.READY,
            )
        }
        if len(assets_by_id) != len(attachment_ids):
            raise PermissionDenied("Every attachment must be a ready upload owned by the sender.")
        assets = [assets_by_id[asset_id] for asset_id in attachment_ids]
        mentioned_users = resolve_message_mentions(
            conversation=locked,
            mentioned_user_ids=set(mentioned_user_ids),
            mention_all=mention_all,
        )
        now = timezone.now()
        locked.last_sequence += 1
        message = Message.objects.create(
            conversation=locked,
            sequence=locked.last_sequence,
            client_message_id=client_message_id,
            author=author,
            body=body,
            kind=kind,
            mention_all=mention_all,
            request_fingerprint=fingerprint,
            reply_to=reply_to,
            forwarded_snapshot=forwarded_snapshot,
        )
        MessageAttachment.objects.bulk_create(
            [
                MessageAttachment(message=message, asset=asset, sort_order=index)
                for index, asset in enumerate(assets)
            ]
        )
        MessageMention.objects.bulk_create(
            [
                MessageMention(message=message, user=user)
                for user in mentioned_users
                if user.pk != author.pk
            ]
        )
        locked.last_message_at = now
        locked.activity_at = now
        locked.save(update_fields=["last_sequence", "last_message_at", "activity_at", "updated_at"])
        ConversationMembership.objects.filter(
            conversation=locked, user=author, left_at__isnull=True
        ).update(
            last_read_sequence=message.sequence,
            last_delivered_sequence=message.sequence,
            read_at=now,
            delivered_at=now,
            is_archived=False,
        )
        message_created_after_commit(locked.pk, message.pk, message.sequence)
        record_audit_event(
            actor=author,
            event_type=(
                AuditEvent.Type.MESSENGER_MESSAGE_FORWARDED
                if forward_message_id is not None
                else AuditEvent.Type.MESSENGER_MESSAGE_SENT
            ),
            target_type=AuditEvent.TargetType.MESSAGE,
            target_id=message.pk,
            new_state={
                "conversation_id": str(locked.pk),
                "sequence": message.sequence,
                "reply_to_id": str(reply_to_id) if reply_to_id else None,
                "attachment_count": len(assets),
                "kind": kind,
                "mention_count": len(mentioned_users),
                "mention_all": mention_all,
            },
        )
        from apps.notifications.models import Notification
        from apps.notifications.services import enqueue_fanout

        enqueue_fanout(
            event_key=f"message:{message.pk}:created",
            event_type=Notification.Type.NEW_MESSAGE,
            source_id=message.pk,
            payload={
                "conversation_id": str(locked.pk),
                "author_id": author.pk,
                "sequence": message.sequence,
            },
        )
        return message, True


@transaction.atomic
def mark_read(conversation: Conversation, *, user: User, sequence: int) -> ConversationMembership:
    locked_conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
    membership = ConversationMembership.objects.select_for_update().get(
        conversation=locked_conversation, user=user, left_at__isnull=True
    )
    if sequence > locked_conversation.last_sequence:
        raise ValidationError("Read sequence cannot exceed the conversation sequence.")
    if sequence <= membership.last_read_sequence:
        return membership
    membership.last_read_sequence = sequence
    membership.last_delivered_sequence = max(membership.last_delivered_sequence, sequence)
    membership.read_at = timezone.now()
    membership.delivered_at = membership.read_at
    membership.save(
        update_fields=[
            "last_read_sequence",
            "last_delivered_sequence",
            "read_at",
            "delivered_at",
        ]
    )
    read_changed_after_commit(locked_conversation.pk, user.pk, sequence)
    return membership


@transaction.atomic
def mark_delivered(
    conversation: Conversation, *, user: User, sequence: int
) -> ConversationMembership:
    locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
    membership = active_membership(locked, user, for_update=True)
    if sequence > locked.last_sequence:
        raise ValidationError("Delivery sequence cannot exceed the conversation sequence.")
    if sequence <= membership.last_delivered_sequence:
        return membership
    membership.last_delivered_sequence = sequence
    membership.delivered_at = timezone.now()
    membership.save(update_fields=["last_delivered_sequence", "delivered_at"])
    read_changed_after_commit(
        locked.pk, user.pk, sequence, event_type="messenger.delivered.changed"
    )
    return membership


@transaction.atomic
def add_group_member(
    conversation: Conversation, *, actor: User, user: User
) -> ConversationMembership:
    locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
    _require_group_admin(locked, actor)
    if locked.type == Conversation.Type.DIRECT:
        raise ValidationError("Direct conversation membership is immutable.")
    if ConversationMembership.objects.filter(
        conversation=locked, user=user, left_at__isnull=True
    ).exists():
        raise ValidationError("User is already an active member.")
    membership = ConversationMembership.objects.create(
        conversation=locked,
        user=user,
        joined_sequence=locked.last_sequence,
        last_read_sequence=locked.last_sequence,
        last_delivered_sequence=locked.last_sequence,
    )
    membership_changed_after_commit("messenger.membership.added", locked.pk, user.pk)
    record_audit_event(
        actor=actor,
        event_type=AuditEvent.Type.MESSENGER_MEMBER_ADDED,
        target_type=AuditEvent.TargetType.CONVERSATION,
        target_id=locked.pk,
        new_state={"user_id": user.pk, "joined_sequence": locked.last_sequence},
    )
    from apps.notifications.models import Notification
    from apps.notifications.services import enqueue_fanout

    enqueue_fanout(
        event_key=f"conversation:{locked.pk}:member:{user.pk}:{membership.pk}",
        event_type=Notification.Type.CHAT_ADDED,
        source_id=locked.pk,
        payload={
            "actor_id": actor.pk,
            "conversation_id": str(locked.pk),
            "recipient_ids": [user.pk],
            "source_type": "CONVERSATION",
        },
    )
    return membership


@transaction.atomic
def remove_group_member(
    conversation: Conversation, *, actor: User, user: User
) -> ConversationMembership:
    locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
    _require_group_admin(locked, actor)
    if locked.type == Conversation.Type.DIRECT:
        raise ValidationError("Direct conversation membership is immutable.")
    membership = active_membership(locked, user, for_update=True)
    if (
        membership.role == ConversationMembership.Role.ADMIN
        and not ConversationMembership.objects.filter(
            conversation=locked,
            role=ConversationMembership.Role.ADMIN,
            left_at__isnull=True,
        )
        .exclude(pk=membership.pk)
        .exists()
    ):
        raise ValidationError("A group must retain an administrator.")
    membership.left_sequence = locked.last_sequence
    membership.left_at = timezone.now()
    membership.save(update_fields=["left_sequence", "left_at"])
    membership_changed_after_commit("messenger.membership.removed", locked.pk, user.pk)
    record_audit_event(
        actor=actor,
        event_type=AuditEvent.Type.MESSENGER_MEMBER_REMOVED,
        target_type=AuditEvent.TargetType.CONVERSATION,
        target_id=locked.pk,
        previous_state={"user_id": user.pk, "role": membership.role},
        new_state={"left_sequence": locked.last_sequence},
    )
    return membership


def _require_group_admin(conversation: Conversation, actor: User) -> ConversationMembership:
    membership = active_membership(conversation, actor, for_update=True)
    if membership.role != ConversationMembership.Role.ADMIN:
        raise PermissionDenied("A conversation administrator is required.")
    return membership


@transaction.atomic
def change_group_role(
    conversation: Conversation,
    *,
    actor: User,
    user: User,
    role: str,
) -> ConversationMembership:
    locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
    _require_group_admin(locked, actor)
    if locked.type == Conversation.Type.DIRECT:
        raise ValidationError("Direct conversation membership is immutable.")
    membership = active_membership(locked, user, for_update=True)
    previous = membership.role
    if previous == role:
        return membership
    if (
        previous == ConversationMembership.Role.ADMIN
        and not ConversationMembership.objects.filter(
            conversation=locked,
            role=ConversationMembership.Role.ADMIN,
            left_at__isnull=True,
        )
        .exclude(pk=membership.pk)
        .exists()
    ):
        raise ValidationError("A group must retain an administrator.")
    membership.role = role
    membership.save(update_fields=["role"])
    membership_changed_after_commit("messenger.membership.role_changed", locked.pk, user.pk)
    record_audit_event(
        actor=actor,
        event_type=AuditEvent.Type.MESSENGER_MEMBER_ROLE_CHANGED,
        target_type=AuditEvent.TargetType.CONVERSATION,
        target_id=locked.pk,
        previous_state={"user_id": user.pk, "role": previous},
        new_state={"user_id": user.pk, "role": role},
    )
    return membership


@transaction.atomic
def leave_group(conversation: Conversation, *, user: User) -> ConversationMembership:
    locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
    if locked.type == Conversation.Type.DIRECT:
        raise ValidationError("Direct conversation membership is immutable.")
    membership = active_membership(locked, user, for_update=True)
    if (
        membership.role == ConversationMembership.Role.ADMIN
        and not ConversationMembership.objects.filter(
            conversation=locked,
            role=ConversationMembership.Role.ADMIN,
            left_at__isnull=True,
        )
        .exclude(pk=membership.pk)
        .exists()
    ):
        raise ValidationError("The last group administrator cannot leave.")
    membership.left_sequence = locked.last_sequence
    membership.left_at = timezone.now()
    membership.save(update_fields=["left_sequence", "left_at"])
    membership_changed_after_commit("messenger.membership.removed", locked.pk, user.pk)
    record_audit_event(
        actor=user,
        event_type=AuditEvent.Type.MESSENGER_MEMBER_REMOVED,
        target_type=AuditEvent.TargetType.CONVERSATION,
        target_id=locked.pk,
        previous_state={"user_id": user.pk, "role": membership.role},
        new_state={"left_sequence": locked.last_sequence, "self_left": True},
    )
    return membership


@transaction.atomic
def edit_message(message: Message, *, actor: User, body: str) -> Message:
    locked = Message.objects.select_for_update().select_related("conversation").get(pk=message.pk)
    active_membership(locked.conversation, actor, for_update=True)
    if locked.author.pk != actor.pk:
        raise PermissionDenied("Only the author can edit this message.")
    if locked.deleted_at is not None:
        raise ValidationError("Deleted messages cannot be edited.")
    normalized = normalize_message_body(body)
    if normalized == locked.body:
        return locked
    MessageRevision.objects.create(message=locked, body=locked.body, edited_by=actor)
    previous = locked.body
    locked.body = normalized
    locked.edited_at = timezone.now()
    locked.save(update_fields=["body", "edited_at"])
    message_changed_after_commit(
        "messenger.message.edited", locked.conversation.pk, locked.pk, locked.sequence
    )
    record_audit_event(
        actor=actor,
        event_type=AuditEvent.Type.MESSENGER_MESSAGE_EDITED,
        target_type=AuditEvent.TargetType.MESSAGE,
        target_id=locked.pk,
        previous_state={"body_sha256": hashlib.sha256(previous.encode()).hexdigest()},
        new_state={"body_sha256": hashlib.sha256(normalized.encode()).hexdigest()},
    )
    return locked


@transaction.atomic
def delete_message(message: Message, *, actor: User) -> Message:
    locked = Message.objects.select_for_update().select_related("conversation").get(pk=message.pk)
    active_membership(locked.conversation, actor, for_update=True)
    if locked.author.pk != actor.pk:
        raise PermissionDenied("Only the author can delete this message.")
    if locked.deleted_at is not None:
        return locked
    MessageRevision.objects.create(message=locked, body=locked.body, edited_by=actor)
    previous_hash = hashlib.sha256(locked.body.encode()).hexdigest()
    locked.body = ""
    locked.deleted_at = timezone.now()
    locked.save(update_fields=["body", "deleted_at"])
    message_changed_after_commit(
        "messenger.message.deleted", locked.conversation.pk, locked.pk, locked.sequence
    )
    record_audit_event(
        actor=actor,
        event_type=AuditEvent.Type.MESSENGER_MESSAGE_DELETED,
        target_type=AuditEvent.TargetType.MESSAGE,
        target_id=locked.pk,
        previous_state={"body_sha256": previous_hash},
        new_state={"deleted_at": locked.deleted_at.isoformat()},
    )
    return locked


@transaction.atomic
def put_message_reaction(message: Message, *, user: User, reaction_type: str) -> MessageReaction:
    locked = Message.objects.select_for_update().select_related("conversation").get(pk=message.pk)
    active_membership(locked.conversation, user, for_update=True)
    if locked.deleted_at is not None:
        raise ValidationError("Deleted messages cannot be reacted to.")
    reaction, _created = MessageReaction.objects.update_or_create(
        message=locked,
        user=user,
        defaults={"reaction_type": reaction_type},
    )
    message_changed_after_commit(
        "messenger.reaction.changed", locked.conversation.pk, locked.pk, locked.sequence
    )
    record_audit_event(
        actor=user,
        event_type=AuditEvent.Type.MESSENGER_REACTION_CHANGED,
        target_type=AuditEvent.TargetType.MESSAGE,
        target_id=locked.pk,
        new_state={"reaction_type": reaction_type},
    )
    return reaction


@transaction.atomic
def delete_message_reaction(message: Message, *, user: User) -> bool:
    locked = Message.objects.select_for_update().select_related("conversation").get(pk=message.pk)
    active_membership(locked.conversation, user, for_update=True)
    deleted, _ = MessageReaction.objects.filter(message=locked, user=user).delete()
    if deleted:
        message_changed_after_commit(
            "messenger.reaction.changed", locked.conversation.pk, locked.pk, locked.sequence
        )
        record_audit_event(
            actor=user,
            event_type=AuditEvent.Type.MESSENGER_REACTION_CHANGED,
            target_type=AuditEvent.TargetType.MESSAGE,
            target_id=locked.pk,
            previous_state={"removed": True},
        )
    return bool(deleted)


def _require_pin_permission(conversation: Conversation, actor: User) -> None:
    membership = active_membership(conversation, actor, for_update=True)
    if (
        conversation.type in {Conversation.Type.GROUP, Conversation.Type.CHANNEL}
        and membership.role != ConversationMembership.Role.ADMIN
    ):
        raise PermissionDenied("A group administrator is required.")


@transaction.atomic
def pin_message(message: Message, *, actor: User) -> PinnedMessage:
    locked = Message.objects.select_for_update().select_related("conversation").get(pk=message.pk)
    _require_pin_permission(locked.conversation, actor)
    if locked.deleted_at is not None:
        raise ValidationError("Deleted messages cannot be pinned.")
    pin, _ = PinnedMessage.objects.get_or_create(
        conversation=locked.conversation,
        message=locked,
        defaults={"pinned_by": actor},
    )
    conversation_changed_after_commit("messenger.message.pinned", locked.conversation.pk)
    record_audit_event(
        actor=actor,
        event_type=AuditEvent.Type.MESSENGER_MESSAGE_PINNED,
        target_type=AuditEvent.TargetType.MESSAGE,
        target_id=locked.pk,
        new_state={"conversation_id": str(locked.conversation.pk)},
    )
    return pin


@transaction.atomic
def unpin_message(message: Message, *, actor: User) -> bool:
    locked = Message.objects.select_for_update().select_related("conversation").get(pk=message.pk)
    _require_pin_permission(locked.conversation, actor)
    deleted, _ = PinnedMessage.objects.filter(
        conversation=locked.conversation, message=locked
    ).delete()
    if deleted:
        conversation_changed_after_commit("messenger.message.unpinned", locked.conversation.pk)
        record_audit_event(
            actor=actor,
            event_type=AuditEvent.Type.MESSENGER_MESSAGE_UNPINNED,
            target_type=AuditEvent.TargetType.MESSAGE,
            target_id=locked.pk,
            previous_state={"conversation_id": str(locked.conversation.pk)},
        )
    return bool(deleted)


_UNSET = object()


@transaction.atomic
def update_conversation_state(
    conversation: Conversation,
    *,
    user: User,
    is_archived: bool | None = None,
    pinned: bool | None = None,
    muted_until=_UNSET,
    draft_body: str | None = None,
    notification_mode: str | None = None,
) -> ConversationMembership:
    locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
    membership = active_membership(locked, user, for_update=True)
    fields: list[str] = []
    if is_archived is not None:
        membership.is_archived = is_archived
        fields.append("is_archived")
    if pinned is not None:
        membership.pinned_at = timezone.now() if pinned else None
        fields.append("pinned_at")
    if muted_until is not _UNSET:
        membership.muted_until = muted_until
        fields.append("muted_until")
    if draft_body is not None:
        membership.draft_body = draft_body[:10_000]
        membership.draft_updated_at = timezone.now()
        fields.extend(["draft_body", "draft_updated_at"])
    if notification_mode is not None:
        membership.notification_mode = notification_mode
        fields.append("notification_mode")
    if fields:
        membership.save(update_fields=fields)
        user_conversation_changed_after_commit("messenger.conversation.updated", locked.pk, user.pk)
    return membership
