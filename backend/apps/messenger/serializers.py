from typing import Any, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.identity.models import User
from apps.publications.serializers import MediaAssetSerializer

from .models import (
    Conversation,
    ConversationMembership,
    Message,
    MessageReaction,
    MessageRevision,
    PinnedMessage,
)
from .services import normalize_message_body


class PersonSerializer(serializers.ModelSerializer):
    org_unit_name = serializers.CharField(source="org_unit.name", allow_null=True, read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = User
        fields = ["id", "username", "full_name", "job_title", "avatar_url", "org_unit_name"]


class MembershipSerializer(serializers.ModelSerializer):
    user = PersonSerializer(read_only=True)
    is_active = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = ConversationMembership
        fields = [
            "id",
            "user",
            "role",
            "joined_at",
            "joined_sequence",
            "left_at",
            "left_sequence",
            "is_active",
            "last_delivered_sequence",
            "delivered_at",
            "last_read_sequence",
            "read_at",
        ]

    def get_is_active(self, membership: ConversationMembership) -> bool:
        return membership.left_at is None


class MessageBodyField(serializers.Field):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Expected a string.")
        if not data:
            return ""
        try:
            return normalize_message_body(data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def to_representation(self, value):
        return value


class MessageWriteSerializer(serializers.Serializer):
    client_message_id = serializers.UUIDField()
    body = MessageBodyField(required=False)
    reply_to_id = serializers.UUIDField(required=False, allow_null=True)
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=10
    )
    forward_message_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        allowed = {
            "client_message_id",
            "body",
            "reply_to_id",
            "attachment_ids",
            "forward_message_id",
        }
        unexpected = set(self.initial_data) - allowed
        if unexpected:
            raise serializers.ValidationError(
                {key: "This field is not allowed." for key in unexpected}
            )
        body = attrs.get("body", "")
        if body:
            try:
                attrs["body"] = normalize_message_body(body)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"body": exc.messages}) from exc
        elif not attrs.get("forward_message_id") and not attrs.get("attachment_ids"):
            raise serializers.ValidationError(
                {"body": "A message requires text, a forward, or an attachment."}
            )
        attrs.setdefault("body", "")
        attachment_ids = attrs.get("attachment_ids", [])
        if len(attachment_ids) != len(set(attachment_ids)):
            raise serializers.ValidationError({"attachment_ids": "Attachments must be unique."})
        return attrs


class ReplyPreviewSerializer(serializers.ModelSerializer):
    author = PersonSerializer(read_only=True)
    body_preview = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Message
        fields = ["id", "author", "body_preview", "deleted_at"]

    def get_body_preview(self, message: Message) -> str:
        return "" if message.deleted_at else message.body[:240]


class MessageSerializer(serializers.ModelSerializer):
    author = PersonSerializer(read_only=True)
    reply_to = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()
    reactions = serializers.SerializerMethodField()
    receipt = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Message
        fields = [
            "id",
            "sequence",
            "client_message_id",
            "author",
            "body",
            "reply_to",
            "forwarded_snapshot",
            "attachments",
            "reactions",
            "edited_at",
            "deleted_at",
            "created_at",
            "receipt",
        ]

    def get_attachments(self, message: Message):
        loaded = getattr(message, "loaded_attachments", None)
        rows = (
            loaded if loaded is not None else cast(Any, message).attachments.select_related("asset")
        )
        return MediaAssetSerializer([row.asset for row in rows], many=True).data

    def get_reply_to(self, message: Message):
        reply = message.reply_to
        if reply is None:
            return None
        intervals: list[tuple[int, int | None]] = self.context.get("visible_intervals", [])
        if not any(
            reply.sequence > joined and (left is None or reply.sequence <= left)
            for joined, left in intervals
        ):
            return None
        return ReplyPreviewSerializer(reply).data

    def get_reactions(self, message: Message):
        rows: list[MessageReaction] = list(
            getattr(
                message,
                "loaded_reactions",
                cast(Any, message).reactions.select_related("user"),
            )
        )
        user = getattr(self.context.get("request"), "user", None)
        user_id = getattr(user, "pk", None)
        return [
            {
                "reaction_type": kind,
                "count": sum(row.reaction_type == kind for row in rows),
                "mine": any(row.reaction_type == kind and row.user.pk == user_id for row in rows),
            }
            for kind in MessageReaction.Type.values
            if any(row.reaction_type == kind for row in rows)
        ]

    def get_receipt(self, message: Message) -> dict[str, int | bool]:
        memberships: list[ConversationMembership] = self.context.get("memberships", [])
        recipients = [
            row
            for row in memberships
            if row.user.pk != message.author.pk
            and row.joined_sequence < message.sequence
            and (row.left_sequence is None or row.left_sequence >= message.sequence)
        ]
        delivered_count = sum(row.last_delivered_sequence >= message.sequence for row in recipients)
        read_count = sum(row.last_read_sequence >= message.sequence for row in recipients)
        payload: dict[str, int | bool] = {
            "delivered_count": delivered_count,
            "read_count": read_count,
            "recipient_count": len(recipients),
        }
        if message.conversation.type == Conversation.Type.DIRECT:
            payload["delivered"] = delivered_count == 1
            payload["read"] = read_count == 1
        return payload


class MessagePreviewSerializer(serializers.ModelSerializer):
    author_id = serializers.IntegerField(read_only=True)
    author_name = serializers.CharField(source="author.full_name", read_only=True)
    body_preview = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Message
        fields = [
            "id",
            "sequence",
            "author_id",
            "author_name",
            "body_preview",
            "created_at",
            "deleted_at",
        ]

    def get_body_preview(self, message: Message) -> str:
        return "" if message.deleted_at else message.body[:240]


class ConversationSummarySerializer(serializers.ModelSerializer):
    peer = serializers.SerializerMethodField()
    member_count = serializers.IntegerField(read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Conversation
        fields = [
            "id",
            "type",
            "title",
            "peer",
            "member_count",
            "last_message",
            "last_message_at",
            "activity_at",
            "unread_count",
            "state",
        ]

    def _current(self, conversation: Conversation) -> ConversationMembership:
        rows = getattr(conversation, "loaded_current_membership", [])
        if rows:
            return rows[0]
        user = self.context["request"].user
        return cast(Any, conversation).memberships.get(user=user, left_at__isnull=True)

    def get_peer(self, conversation: Conversation):
        if conversation.type != Conversation.Type.DIRECT:
            return None
        user_id = self.context["request"].user.pk
        rows = getattr(conversation, "loaded_direct_memberships", [])
        peer = next((row.user for row in rows if row.user_id != user_id), None)
        return PersonSerializer(peer).data if peer else None

    def get_last_message(self, conversation: Conversation):
        messages: list[Message] = getattr(conversation, "loaded_last_messages", [])
        if not messages:
            return None
        current = self._current(conversation)
        message = messages[0]
        if message.sequence <= current.joined_sequence:
            return None
        return MessagePreviewSerializer(message).data

    def get_unread_count(self, conversation: Conversation) -> int:
        current = self._current(conversation)
        visible_floor = max(current.last_read_sequence, current.joined_sequence)
        return max(0, conversation.last_sequence - visible_floor)

    def get_state(self, conversation: Conversation):
        current = self._current(conversation)
        return {
            "is_archived": current.is_archived,
            "pinned_at": current.pinned_at,
            "muted_until": current.muted_until,
            "draft_body": current.draft_body,
            "draft_updated_at": current.draft_updated_at,
        }


class ConversationDetailSerializer(serializers.ModelSerializer):
    created_by_id = serializers.IntegerField(read_only=True)
    pinned_messages = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Conversation
        fields = [
            "id",
            "type",
            "title",
            "created_by_id",
            "last_sequence",
            "last_message_at",
            "activity_at",
            "created_at",
            "pinned_messages",
        ]

    def get_pinned_messages(self, conversation: Conversation):
        rows: list[PinnedMessage] = list(
            getattr(
                conversation,
                "loaded_pinned_messages",
                cast(Any, conversation).pinned_messages.select_related("message__author")[:20],
            )
        )
        intervals: list[tuple[int, int | None]] = self.context.get("visible_intervals", [])
        visible = [
            row.message
            for row in rows
            if any(
                row.message.sequence > joined and (left is None or row.message.sequence <= left)
                for joined, left in intervals
            )
        ]
        return MessagePreviewSerializer(visible, many=True).data


ConversationSerializer = ConversationDetailSerializer


class DirectConversationSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1)


class GroupConversationSerializer(serializers.Serializer):
    title = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True)
    member_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), min_length=1, max_length=200
    )

    def validate_member_ids(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError("Members must be unique.")
        return values


class ReadSerializer(serializers.Serializer):
    sequence = serializers.IntegerField(min_value=0)


class MemberInputSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1)


class MemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=ConversationMembership.Role.choices)


class MessageEditSerializer(serializers.Serializer):
    body = MessageBodyField()


class MessageReactionWriteSerializer(serializers.Serializer):
    reaction_type = serializers.ChoiceField(choices=MessageReaction.Type.choices)


class MessageRevisionSerializer(serializers.ModelSerializer):
    edited_by = PersonSerializer(read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = MessageRevision
        fields = ["id", "body", "edited_by", "created_at"]


class MessageSearchSerializer(serializers.Serializer):
    q = serializers.CharField(min_length=1, max_length=200, trim_whitespace=True)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=50)


class ConversationStateSerializer(serializers.Serializer):
    is_archived = serializers.BooleanField(required=False)
    pinned = serializers.BooleanField(required=False)
    muted_until = serializers.DateTimeField(required=False, allow_null=True)
    draft_body = serializers.CharField(
        required=False, allow_blank=True, max_length=10_000, trim_whitespace=False
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("At least one state field is required.")
        return attrs
