import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Conversation(models.Model):
    class Type(models.TextChoices):
        DIRECT = "DIRECT", "Direct"
        GROUP = "GROUP", "Group"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=8, choices=Type)
    title = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_conversations",
    )
    last_sequence = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]

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
        ADMIN = "ADMIN", "Admin"

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

    class Meta:
        ordering = ["joined_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "user"], name="messenger_membership_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.conversation.pk}: {self.user.pk}"


class Message(models.Model):
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
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
