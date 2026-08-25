from urllib.parse import urlsplit

from django.conf import settings
from rest_framework import serializers

from apps.identity.models import User

from .models import Notification, NotificationPreference


class NotificationActorSerializer(serializers.ModelSerializer):
    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = User
        fields = ["id", "full_name", "avatar_url"]


class NotificationSerializer(serializers.ModelSerializer):
    actor = NotificationActorSerializer(read_only=True)
    target_url = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Notification
        fields = [
            "id",
            "notification_type",
            "actor",
            "source_type",
            "source_id",
            "publication_id",
            "conversation_id",
            "occurrence_count",
            "event_version",
            "created_at",
            "last_event_at",
            "read_at",
            "target_url",
        ]

    def get_target_url(self, notification: Notification) -> str:
        if notification.conversation_id:
            base = f"/messages?conversation={notification.conversation_id}"
            return (
                f"{base}&message={notification.source_id}"
                if notification.source_type == "MESSAGE"
                else base
            )
        if notification.publication_id:
            base = f"/news/{notification.publication_id}"
            return (
                f"{base}?comment={notification.source_id}"
                if notification.source_type == "COMMENT"
                else base
            )
        return "/notifications"


class PreferenceSerializer(serializers.Serializer):
    notification_type = serializers.ChoiceField(choices=Notification.Type.choices)
    in_app_enabled = serializers.BooleanField()
    push_enabled = serializers.BooleanField()
    email_enabled = serializers.BooleanField()


class NotificationSettingsWriteSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    preferences = PreferenceSerializer(many=True, required=False)

    def validate_preferences(self, values):
        kinds = [value["notification_type"] for value in values]
        if len(kinds) != len(set(kinds)):
            raise serializers.ValidationError("Notification types must be unique.")
        return values

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("At least one setting is required.")
        return attrs


def settings_payload(user: User) -> dict[str, object]:
    enabled = getattr(getattr(user, "notification_settings", None), "enabled", True)
    rows = {row.notification_type: row for row in NotificationPreference.objects.filter(user=user)}
    return {
        "enabled": enabled,
        "preferences": [
            {
                "notification_type": kind,
                "in_app_enabled": rows[kind].in_app_enabled if kind in rows else True,
                "push_enabled": rows[kind].push_enabled if kind in rows else False,
                "email_enabled": (
                    rows[kind].email_enabled
                    if kind in rows
                    else kind == Notification.Type.ACK_REQUIRED
                ),
            }
            for kind in Notification.Type.values
        ],
    }


class PushSubscriptionSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=4096, write_only=True)
    p256dh = serializers.CharField(max_length=1024, write_only=True)
    auth = serializers.CharField(max_length=1024, write_only=True)

    def validate_endpoint(self, value):
        parsed = urlsplit(value)
        host = (parsed.hostname or "").casefold()
        allowed = settings.WEB_PUSH_ALLOWED_HOST_SUFFIXES
        try:
            port = parsed.port
        except ValueError as exc:
            raise serializers.ValidationError("This Web Push service is not allowed.") from exc
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
            or not any(host == suffix or host.endswith(f".{suffix}") for suffix in allowed)
        ):
            raise serializers.ValidationError("This Web Push service is not allowed.")
        return value
