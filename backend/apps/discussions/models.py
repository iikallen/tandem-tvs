import uuid

from django.conf import settings
from django.db import models


class Comment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DELETED = "DELETED", "Deleted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    publication = models.ForeignKey(
        "publications.Publication", on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="comments"
    )
    body = models.TextField(max_length=5_000, blank=True)
    status = models.CharField(max_length=16, choices=Status, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["publication", "status", "created_at", "id"], name="comment_pub_page_idx"
            ),
            models.Index(fields=["author", "-created_at"], name="comment_author_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(status="ACTIVE", deleted_at__isnull=True)
                    | models.Q(status="DELETED", deleted_at__isnull=False, body="")
                ),
                name="comment_deleted_shape",
            )
        ]

    def __str__(self) -> str:
        return f"{self.publication.pk}: {self.author.pk}"


class Reaction(models.Model):
    class Type(models.TextChoices):
        LIKE = "LIKE", "Like"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    publication = models.ForeignKey(
        "publications.Publication", on_delete=models.CASCADE, related_name="reactions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reactions"
    )
    reaction_type = models.CharField(max_length=16, choices=Type)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["publication", "reaction_type"], name="reaction_pub_type_idx"),
            models.Index(fields=["user", "-created_at"], name="reaction_user_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["publication", "user", "reaction_type"],
                name="reaction_publication_user_type_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.publication.pk}: {self.user.pk} {self.reaction_type}"
