import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Conversation(models.Model):
    class Type(models.TextChoices):
        DIRECT = "DIRECT", "Direct"
        GROUP = "GROUP", "Group"
        CHANNEL = "CHANNEL", "Channel"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=8, choices=Type)
    title = models.CharField(max_length=255, blank=True)
    discussion_enabled = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_conversations",
    )
    last_sequence = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    activity_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-activity_at", "-id"]
        indexes = [models.Index(fields=["-activity_at", "-id"], name="messenger_activity_idx")]

    def __str__(self) -> str:
        return f"{self.type} {self.pk}"


class DirectConversationPair(models.Model):
    conversation = models.OneToOneField(
        Conversation,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="direct_pair",
    )
    user_low = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="direct_pairs_low",
    )
    user_high = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="direct_pairs_high",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_low", "user_high"], name="messenger_direct_pair_unique"
            ),
            models.CheckConstraint(
                condition=Q(user_low__lt=F("user_high")), name="messenger_direct_pair_ordered"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_low.pk}:{self.user_high.pk}"


class ConversationMembership(models.Model):
    class Role(models.TextChoices):
        MEMBER = "MEMBER", "Member"
        WRITER = "WRITER", "Writer"
        ADMIN = "ADMIN", "Admin"

    class NotificationMode(models.TextChoices):
        ALL = "ALL", "All"
        MENTIONS = "MENTIONS", "Mentions"
        NONE = "NONE", "None"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="conversation_memberships",
    )
    role = models.CharField(max_length=8, choices=Role, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_sequence = models.PositiveBigIntegerField(default=0)
    read_at = models.DateTimeField(null=True, blank=True)
    last_delivered_sequence = models.PositiveBigIntegerField(default=0)
    delivered_at = models.DateTimeField(null=True, blank=True)
    joined_sequence = models.PositiveBigIntegerField(default=0)
    left_sequence = models.PositiveBigIntegerField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)
    pinned_at = models.DateTimeField(null=True, blank=True)
    muted_until = models.DateTimeField(null=True, blank=True)
    notification_mode = models.CharField(
        max_length=8, choices=NotificationMode, default=NotificationMode.ALL
    )
    draft_body = models.TextField(blank=True)
    draft_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["joined_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "user"],
                condition=Q(left_at__isnull=True),
                name="messenger_active_membership_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(left_at__isnull=True, left_sequence__isnull=True)
                    | Q(left_at__isnull=False, left_sequence__isnull=False)
                ),
                name="messenger_membership_left_state",
            ),
            models.CheckConstraint(
                condition=Q(left_sequence__isnull=True)
                | Q(left_sequence__gte=F("joined_sequence")),
                name="messenger_membership_sequence_range",
            ),
            models.CheckConstraint(
                condition=Q(last_delivered_sequence__gte=F("last_read_sequence")),
                name="messenger_delivery_covers_read",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.conversation.pk}: {self.user.pk}"


class Message(models.Model):
    class Kind(models.TextChoices):
        CHAT = "CHAT", "Chat message"
        CHANNEL_POST = "CHANNEL_POST", "Channel post"
        DISCUSSION = "DISCUSSION", "Discussion"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sequence = models.PositiveBigIntegerField()
    client_message_id = models.UUIDField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="messenger_messages",
    )
    body = models.TextField()
    kind = models.CharField(max_length=16, choices=Kind, default=Kind.CHAT)
    mention_all = models.BooleanField(default=False)
    request_fingerprint = models.CharField(max_length=64)
    reply_to = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="replies",
    )
    forwarded_snapshot = models.JSONField(null=True, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        indexes = [
            GinIndex(SearchVector("body", config="russian"), name="msg_search_ru_idx"),
            GinIndex(SearchVector("body", config="tandem_kazakh"), name="msg_search_kk_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "sequence"], name="messenger_message_sequence_unique"
            ),
            models.UniqueConstraint(
                fields=["conversation", "author", "client_message_id"],
                name="messenger_message_client_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.conversation.pk}#{self.sequence}"


class MessageMention(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="mentions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="message_mentions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "user"], name="messenger_message_mention_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.message.pk}:{self.user.pk}"


class MessageRevisionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Message revisions are append-only.")

    def delete(self):
        raise ValidationError("Message revisions are append-only.")


class MessageRevision(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="revisions")
    body = models.TextField()
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="messenger_message_revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = MessageRevisionQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.message.pk}@{self.pk}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Message revisions are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Message revisions are append-only.")


class MessageReaction(models.Model):
    class Type(models.TextChoices):
        LIKE = "LIKE", "Like"
        LOVE = "LOVE", "Love"
        LAUGH = "LAUGH", "Laugh"
        WOW = "WOW", "Wow"
        SAD = "SAD", "Sad"

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="messenger_message_reactions",
    )
    reaction_type = models.CharField(max_length=16, choices=Type)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "user"], name="messenger_reaction_user_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.message.pk}:{self.user.pk}:{self.reaction_type}"


class MessageAttachment(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="attachments")
    asset = models.ForeignKey(
        "publications.MediaAsset",
        on_delete=models.PROTECT,
        related_name="messenger_attachments",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["message", "asset"], name="messenger_message_asset_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.message.pk}:{self.asset.pk}"


class PinnedMessage(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="pinned_messages"
    )
    message = models.ForeignKey(Message, on_delete=models.PROTECT, related_name="pins")
    pinned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="messenger_pins",
    )
    pinned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-pinned_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "message"], name="messenger_pinned_message_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.conversation.pk}:{self.message.pk}"
