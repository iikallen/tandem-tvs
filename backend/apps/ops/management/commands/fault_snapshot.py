import hashlib
import json

from django.core.management.base import BaseCommand

from apps.messenger.models import Message
from apps.notifications.models import Notification
from apps.publications.models import MediaAsset, Publication


def digest(queryset, fields: tuple[str, ...]) -> dict[str, object]:
    checksum = hashlib.sha256()
    count = 0
    for row in queryset.order_by("pk").values_list(*fields).iterator(chunk_size=1_000):
        checksum.update(json.dumps(row, default=str, ensure_ascii=False).encode())
        checksum.update(b"\n")
        count += 1
    return {"count": count, "sha256": checksum.hexdigest()}


class Command(BaseCommand):
    help = "Print stable source-data digests used by the isolated fault matrix."

    def handle(self, *args, **options):
        snapshot = {
            "media": digest(
                MediaAsset.objects.all(),
                ("pk", "storage_key", "size", "sha256", "status"),
            ),
            "messages": digest(
                Message.objects.all(),
                ("pk", "conversation_id", "sequence", "author_id", "body", "deleted_at"),
            ),
            "notifications": digest(
                Notification.objects.all(),
                ("pk", "recipient_id", "dedupe_key", "occurrence_count", "event_version"),
            ),
            "publications": digest(
                Publication.objects.all(),
                ("pk", "title", "status", "body_text", "published_at"),
            ),
        }
        self.stdout.write(json.dumps(snapshot, sort_keys=True, separators=(",", ":")))
