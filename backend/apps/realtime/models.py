import uuid

from django.db import models
from django.utils import timezone


class RealtimeOutboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group_name = models.CharField(max_length=100)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["delivered_at", "available_at", "created_at"],
                name="realtime_outbox_pending_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.event_type}: {self.pk}"
