import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Notification(models.Model):
    class Type(models.TextChoices):
        NEW_PUBLICATION = "NEW_PUBLICATION", "New publication"
        ACK_REQUIRED = "ACK_REQUIRED", "Acknowledgement required"
        COMMENT_REPLY = "COMMENT_REPLY", "Comment reply"
        COMMENT_MENTION = "COMMENT_MENTION", "Comment mention"
        NEW_MESSAGE = "NEW_MESSAGE", "New message"
        MESSAGE_MENTION = "MESSAGE_MENTION", "Message mention"
        CHAT_ADDED = "CHAT_ADDED", "Added to chat"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="unified_notifications",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notification_actions",
    )
    notification_type = models.CharField(max_length=32, choices=Type)
    source_type = models.CharField(max_length=32)
    source_id = models.UUIDField()
    publication_id = models.UUIDField(null=True, blank=True)
    conversation_id = models.UUIDField(null=True, blank=True)
    dedupe_key = models.CharField(max_length=160)
    occurrence_count = models.PositiveIntegerField(default=1)
    event_version = models.PositiveIntegerField(default=1)
    payload = models.JSONField(default=dict, blank=True)
    in_app_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_event_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_event_at", "-id"]
        indexes = [
            models.Index(
                fields=["recipient", "read_at", "-last_event_at"],
                name="notification_inbox_idx",
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "dedupe_key"],
                condition=Q(read_at__isnull=True),
                name="notification_unread_group_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.recipient.pk}: {self.notification_type}"


class NotificationFanoutEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_key = models.CharField(max_length=200, unique=True)
    event_type = models.CharField(max_length=32, choices=Notification.Type)
    source_id = models.UUIDField()
    payload = models.JSONField(default=dict)
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["processed_at", "available_at"], name="notif_fanout_pending_idx")
        ]

    def __str__(self) -> str:
        return self.event_key


class NotificationSettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_settings",
    )
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return str(self.user.pk)


class NotificationPreference(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    notification_type = models.CharField(max_length=32, choices=Notification.Type)
    in_app_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=False)
    email_enabled = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "notification_type"], name="notification_preference_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user.pk}: {self.notification_type}"


class PushSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"PushSubscription(user={self.user.pk}, endpoint=[redacted])"


class NotificationDelivery(models.Model):
    class Channel(models.TextChoices):
        PUSH = "PUSH", "Push"
        EMAIL = "EMAIL", "Email"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"
        DISABLED = "DISABLED", "Disabled"

    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="deliveries"
    )
    channel = models.CharField(max_length=8, choices=Channel)
    event_version = models.PositiveIntegerField()
    status = models.CharField(max_length=8, choices=Status, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["notification", "channel", "event_version"],
                name="notification_delivery_unique",
            )
        ]
        indexes = [
            models.Index(fields=["status", "available_at"], name="notification_delivery_idx")
        ]

    def __str__(self) -> str:
        return f"{self.notification.pk}: {self.channel}: {self.status}"
