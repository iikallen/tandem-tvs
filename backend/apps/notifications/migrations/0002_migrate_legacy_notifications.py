from django.db import migrations


def migrate_legacy(apps, schema_editor):
    LegacyNotification = apps.get_model("discussions", "Notification")
    Notification = apps.get_model("notifications", "Notification")
    rows = []

    def flush():
        original_times = [(row.created_at, row.last_event_at, row.read_at) for row in rows]
        Notification.objects.bulk_create(rows)
        for row, (created_at, last_event_at, read_at) in zip(rows, original_times, strict=True):
            row.created_at = created_at
            row.last_event_at = last_event_at
            row.read_at = read_at
        Notification.objects.bulk_update(rows, ["created_at", "last_event_at", "read_at"])

    for legacy in LegacyNotification.objects.all().iterator(chunk_size=500):
        rows.append(
            Notification(
                id=legacy.id,
                recipient_id=legacy.recipient_id,
                actor_id=legacy.actor_id,
                notification_type=legacy.notification_type,
                source_type="COMMENT",
                source_id=legacy.comment_id,
                publication_id=legacy.publication_id,
                dedupe_key=f"{legacy.notification_type}:{legacy.comment_id}",
                created_at=legacy.created_at,
                last_event_at=legacy.created_at,
                read_at=legacy.read_at,
            )
        )
        if len(rows) == 500:
            flush()
            rows = []
    if rows:
        flush()


class Migration(migrations.Migration):
    dependencies = [
        ("discussions", "0002_commentattachment_commentmention_commentreport_and_more"),
        ("notifications", "0001_initial"),
    ]

    operations = [migrations.RunPython(migrate_legacy, migrations.RunPython.noop)]
