import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.db import models


def default_reaction_types() -> list[str]:
    return ["LIKE"]


class EngagementSettings(models.Model):
    comment_edit_window_minutes = models.PositiveIntegerField(default=60)
    comment_delete_window_minutes = models.PositiveIntegerField(default=60)
    enabled_reaction_types = models.JSONField(default=default_reaction_types)
    max_comment_attachments = models.PositiveSmallIntegerField(default=5)
    max_comment_attachment_bytes = models.PositiveIntegerField(default=25 * 1024 * 1024)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return "Engagement settings"

    @classmethod
    def load(cls):
        row, _ = cls.objects.get_or_create(pk=1)
        return row


class StopWord(models.Model):
    value = models.CharField(max_length=100, unique=True)
    normalized_value = models.CharField(max_length=100, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["value", "id"]

    def __str__(self) -> str:
        return self.value


class Comment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DELETED = "DELETED", "Deleted by author"
        HIDDEN = "HIDDEN", "Hidden for moderation"
        REMOVED = "REMOVED", "Removed by moderator"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    publication = models.ForeignKey(
        "publications.Publication", on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="comments"
    )
    thread_root = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="thread_replies"
    )
    reply_to = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="direct_replies"
    )
    body = models.TextField(max_length=5_000, blank=True)
    status = models.CharField(max_length=16, choices=Status, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["publication", "thread_root", "-created_at", "-id"],
                name="comment_thread_page_idx",
            ),
            models.Index(fields=["reply_to"], name="comment_reply_to_idx"),
            models.Index(fields=["author", "-created_at"], name="comment_author_idx"),
            GinIndex(SearchVector("body", config="russian"), name="comment_search_ru_idx"),
            GinIndex(SearchVector("body", config="tandem_kazakh"), name="comment_search_kk_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(thread_root__isnull=True, reply_to__isnull=True)
                    | models.Q(thread_root__isnull=False, reply_to__isnull=False)
                ),
                name="comment_thread_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="ACTIVE", deleted_at__isnull=True)
                    | models.Q(status="HIDDEN", deleted_at__isnull=True)
                    | models.Q(status="DELETED", deleted_at__isnull=False, body="")
                    | models.Q(status="REMOVED", deleted_at__isnull=False)
                ),
                name="comment_status_shape",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.publication.pk}: {self.author.pk}"


class CommentMention(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="mentions")
    mentioned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="comment_mentions"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["comment", "mentioned_user"], name="comment_mention_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.comment.pk}: {self.mentioned_user.pk}"


class CommentAttachment(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="attachments")
    asset = models.ForeignKey(
        "publications.MediaAsset", on_delete=models.PROTECT, related_name="comment_attachments"
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["comment", "asset"], name="comment_attachment_unique")
        ]

    def __str__(self) -> str:
        return f"{self.comment.pk}: {self.asset.pk}"


class Reaction(models.Model):
    class Type(models.TextChoices):
        LIKE = "LIKE", "Like"
        CELEBRATE = "CELEBRATE", "Celebrate"
        SUPPORT = "SUPPORT", "Support"
        INSIGHTFUL = "INSIGHTFUL", "Insightful"
        THANKS = "THANKS", "Thanks"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    publication = models.ForeignKey(
        "publications.Publication",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reactions",
    )
    comment = models.ForeignKey(
        Comment, null=True, blank=True, on_delete=models.CASCADE, related_name="reactions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reactions"
    )
    reaction_type = models.CharField(max_length=16, choices=Type)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["publication", "reaction_type"], name="reaction_pub_type_idx"),
            models.Index(fields=["comment", "reaction_type"], name="reaction_comment_type_idx"),
            models.Index(fields=["user", "-created_at"], name="reaction_user_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(publication__isnull=False, comment__isnull=True)
                    | models.Q(publication__isnull=True, comment__isnull=False)
                ),
                name="reaction_exactly_one_target",
            ),
            models.UniqueConstraint(
                fields=["publication", "user"],
                condition=models.Q(publication__isnull=False),
                name="reaction_publication_user_unique",
            ),
            models.UniqueConstraint(
                fields=["comment", "user"],
                condition=models.Q(comment__isnull=False),
                name="reaction_comment_user_unique",
            ),
        ]

    def __str__(self) -> str:
        target = self.publication.pk if self.publication else self.comment.pk
        return f"{target}: {self.user.pk} {self.reaction_type}"


class CommentReport(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        RESOLVED = "RESOLVED", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    comment = models.ForeignKey(Comment, on_delete=models.PROTECT, related_name="reports")
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="comment_reports"
    )
    reason = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=16, choices=Status, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="resolved_comment_reports",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["status", "-created_at"], name="comment_report_queue_idx")]
        constraints = [
            models.UniqueConstraint(fields=["comment", "reporter"], name="comment_reporter_unique")
        ]

    def __str__(self) -> str:
        return f"{self.comment.pk}: {self.status}"


class ModerationFlag(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.PROTECT, related_name="flags")
    matched_word = models.CharField(max_length=100)
    is_open = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["comment", "matched_word"], name="comment_flag_word_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.comment.pk}: {self.matched_word}"


class CommentRestriction(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="comment_restrictions"
    )
    reason = models.CharField(max_length=500, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_restrictions"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "revoked_at", "expires_at"], name="restriction_active_idx")
        ]

    def __str__(self) -> str:
        return f"{self.user.pk}: {self.expires_at or 'indefinite'}"
