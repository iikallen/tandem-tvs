from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.publications.serializers import UserSummarySerializer

from .models import Comment, Reaction
from .services import normalize_comment_body


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

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"body"}
        if unexpected:
            raise serializers.ValidationError(
                {key: "This field is not allowed." for key in unexpected}
            )
        return attrs


class CommentSerializer(serializers.ModelSerializer):
    author = UserSummarySerializer(read_only=True)
    body = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Comment
        fields = [
            "id",
            "author",
            "body",
            "status",
            "created_at",
            "updated_at",
            "edited_at",
            "deleted_at",
        ]

    def get_body(self, obj: Comment) -> str | None:
        return obj.body if obj.status == Comment.Status.ACTIVE else None


class ReactionTypeSerializer(serializers.Serializer):
    reaction_type = serializers.ChoiceField(choices=Reaction.Type.choices)


class ReactionSerializer(serializers.ModelSerializer):
    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Reaction
        fields = ["id", "reaction_type"]


class ReactionSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    counts = serializers.DictField(child=serializers.IntegerField())
    mine = serializers.ListField(child=serializers.CharField())


class RealtimeTicketSerializer(serializers.Serializer):
    publication_id = serializers.UUIDField()

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"publication_id"}
        if unexpected:
            raise serializers.ValidationError(
                {key: "This field is not allowed." for key in unexpected}
            )
        return attrs
