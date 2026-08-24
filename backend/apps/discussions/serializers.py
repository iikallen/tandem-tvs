from datetime import timedelta
from typing import Any, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from apps.identity.models import User
from apps.publications.models import MediaAsset
from apps.publications.serializers import MediaAssetSerializer, UserSummarySerializer

from .models import (
    Comment,
    CommentReport,
    EngagementSettings,
    Notification,
    Reaction,
    StopWord,
)
from .services import normalize_comment_body, normalize_stop_word


class CommentBodyField(serializers.Field):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Expected a string.")
        try:
            return normalize_comment_body(data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def to_representation(self, value):
        return value


class CommentWriteSerializer(serializers.Serializer):
    body = CommentBodyField()
    reply_to = serializers.UUIDField(required=False, allow_null=True)
    mentions = serializers.ListField(
        child=serializers.CharField(max_length=128), required=False, default=list, max_length=50
    )
    attachments = serializers.PrimaryKeyRelatedField(
        queryset=MediaAsset.objects.filter(status=MediaAsset.Status.READY),
        many=True,
        required=False,
        default=list,
    )

    def validate(self, attrs):
        allowed = {"body", "reply_to", "mentions", "attachments"}
        unexpected = set(self.initial_data) - allowed
        if unexpected:
            raise serializers.ValidationError(
                {key: "This field is not allowed." for key in unexpected}
            )
        portal_ids = attrs["mentions"]
        users = list(User.objects.filter(portal_id__in=portal_ids, is_active=True))
        if len(users) != len(set(portal_ids)):
            raise serializers.ValidationError({"mentions": "Employee is unknown or inactive."})
        attrs["mentioned_users"] = users
        return attrs


class CommentSerializer(serializers.ModelSerializer):
    author = UserSummarySerializer(read_only=True)
    body = serializers.SerializerMethodField()
    reply_to = serializers.UUIDField(source="reply_to_id", allow_null=True, read_only=True)
    thread_root = serializers.UUIDField(source="thread_root_id", allow_null=True, read_only=True)
    reply_to_author = serializers.SerializerMethodField()
    reply_count = serializers.IntegerField(read_only=True, default=0)
    reaction_count = serializers.IntegerField(read_only=True, default=0)
    preview_replies = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()
    mentions = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Comment
        fields = [
            "id",
            "author",
            "body",
            "status",
            "thread_root",
            "reply_to",
            "reply_to_author",
            "reply_count",
            "reaction_count",
            "preview_replies",
            "attachments",
            "mentions",
            "can_edit",
            "can_delete",
            "created_at",
            "updated_at",
            "edited_at",
            "deleted_at",
        ]

    def get_body(self, obj: Comment) -> str | None:
        return obj.body if obj.status == Comment.Status.ACTIVE else None

    def get_reply_to_author(self, obj: Comment) -> str | None:
        return obj.reply_to.author.full_name if obj.reply_to is not None else None

    def get_preview_replies(self, obj: Comment):
        replies = getattr(obj, "preview_items", [])
        return CommentSerializer(replies, many=True, context=self.context).data

    def get_mentions(self, obj: Comment):
        return [item.mentioned_user.portal_id for item in cast(Any, obj).mentions.all()]

    def get_attachments(self, obj: Comment):
        if obj.status != Comment.Status.ACTIVE:
            return []
        return MediaAssetSerializer(
            [item.asset for item in cast(Any, obj).attachments.all()], many=True
        ).data

    def _can_mutate(self, obj: Comment, kind: str) -> bool:
        request = self.context.get("request")
        if (
            request is None
            or request.user.pk != obj.author.pk
            or obj.status != Comment.Status.ACTIVE
        ):
            return False
        settings_row = EngagementSettings.load()
        minutes = getattr(settings_row, f"comment_{kind}_window_minutes")
        return timezone.now() < obj.created_at + timedelta(minutes=minutes)

    def get_can_edit(self, obj: Comment) -> bool:
        return self._can_mutate(obj, "edit")

    def get_can_delete(self, obj: Comment) -> bool:
        return self._can_mutate(obj, "delete")


class ReactionSerializer(serializers.ModelSerializer):
    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Reaction
        fields = ["id", "reaction_type"]


class ReactionSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    counts = serializers.DictField(child=serializers.IntegerField())
    mine = serializers.ListField(child=serializers.CharField())
    actors = serializers.DictField(child=UserSummarySerializer(many=True), required=False)
    enabled_types = serializers.ListField(child=serializers.CharField())


class RealtimeTicketSerializer(serializers.Serializer):
    publication_id = serializers.UUIDField()

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"publication_id"}
        if unexpected:
            raise serializers.ValidationError(
                {key: "This field is not allowed." for key in unexpected}
            )
        return attrs


class CommentReportSerializer(serializers.ModelSerializer):
    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = CommentReport
        fields = ["id", "reason", "status", "created_at"]
        read_only_fields = ["id", "status", "created_at"]


class StopWordSerializer(serializers.ModelSerializer):
    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = StopWord
        fields = ["id", "value", "is_active"]
        read_only_fields = ["id"]

    def validate_value(self, value):
        return normalize_stop_word(value)

    def create(self, validated_data):
        normalized = normalize_stop_word(validated_data["value"])
        validated_data["normalized_value"] = normalized
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "value" in validated_data:
            validated_data["normalized_value"] = normalize_stop_word(validated_data["value"])
        return super().update(instance, validated_data)


class EngagementSettingsSerializer(serializers.ModelSerializer):
    stop_words = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = EngagementSettings
        fields = [
            "comment_edit_window_minutes",
            "comment_delete_window_minutes",
            "enabled_reaction_types",
            "max_comment_attachments",
            "max_comment_attachment_bytes",
            "stop_words",
            "updated_at",
        ]
        read_only_fields = ["updated_at", "stop_words"]

    def validate_enabled_reaction_types(self, values):
        if not isinstance(values, list) or not values or len(values) != len(set(values)):
            raise serializers.ValidationError("Choose one or more unique reaction types.")
        if any(value not in Reaction.Type.values for value in values):
            raise serializers.ValidationError("Unknown reaction type.")
        return values

    def get_stop_words(self, _obj):
        return StopWordSerializer(StopWord.objects.all(), many=True).data


class NotificationSerializer(serializers.ModelSerializer):
    actor = UserSummarySerializer(read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Notification
        fields = [
            "id",
            "notification_type",
            "actor",
            "publication_id",
            "comment_id",
            "created_at",
            "read_at",
        ]
