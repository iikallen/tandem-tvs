from typing import Any, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.identity.models import User

from .models import Conversation, ConversationMembership, Message
from .services import normalize_message_body


class PersonSerializer(serializers.ModelSerializer):
    org_unit_name = serializers.CharField(source="org_unit.name", allow_null=True, read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = User
        fields = ["id", "username", "full_name", "job_title", "avatar_url", "org_unit_name"]


class MembershipSerializer(serializers.ModelSerializer):
    user = PersonSerializer(read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = ConversationMembership
        fields = ["user", "role", "joined_at", "last_read_sequence", "read_at"]


class MessageBodyField(serializers.Field):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Expected a string.")
        try:
            return normalize_message_body(data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def to_representation(self, value):
        return value


class MessageWriteSerializer(serializers.Serializer):
    client_message_id = serializers.UUIDField()
    body = MessageBodyField()

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"client_message_id", "body"}
        if unexpected:
            raise serializers.ValidationError(
                {key: "This field is not allowed." for key in unexpected}
            )
        return attrs


class MessageSerializer(serializers.ModelSerializer):
    author = PersonSerializer(read_only=True)
    receipt = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Message
        fields = [
            "id",
            "sequence",
            "client_message_id",
            "author",
            "body",
            "created_at",
            "receipt",
        ]

    def get_receipt(self, message: Message) -> dict[str, int | bool]:
        memberships: list[ConversationMembership] = self.context.get("memberships", [])
        recipients = [row for row in memberships if row.user.pk != message.author.pk]
        read_count = sum(row.last_read_sequence >= message.sequence for row in recipients)
        payload: dict[str, int | bool] = {
            "read_count": read_count,
            "recipient_count": len(recipients),
        }
        if message.conversation.type == Conversation.Type.DIRECT:
            payload["read"] = read_count == 1
        return payload


class ConversationSerializer(serializers.ModelSerializer):
    created_by_id = serializers.IntegerField(read_only=True)
    members = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Conversation
        fields = [
            "id",
            "type",
            "title",
            "created_by_id",
            "last_sequence",
            "last_message_at",
            "created_at",
            "members",
            "last_message",
            "unread_count",
        ]

    @staticmethod
    def _members(conversation: Conversation) -> list[ConversationMembership]:
        loaded = getattr(conversation, "loaded_memberships", None)
        return loaded if loaded is not None else list(cast(Any, conversation).memberships.all())

    def get_members(self, conversation: Conversation):
        return MembershipSerializer(self._members(conversation), many=True).data

    def get_last_message(self, conversation: Conversation):
        messages: list[Message] = getattr(conversation, "loaded_last_messages", [])
        if not messages:
            return None
        return MessageSerializer(
            messages[0], context={"memberships": self._members(conversation)}
        ).data

    def get_unread_count(self, conversation: Conversation) -> int:
        user_id = self.context["request"].user.pk
        current = next(row for row in self._members(conversation) if row.user.pk == user_id)
        return max(0, conversation.last_sequence - current.last_read_sequence)


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
