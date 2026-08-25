import uuid

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="RealtimeOutboxEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("group_name", models.CharField(max_length=100)),
                ("event_type", models.CharField(max_length=100)),
                ("payload", models.JSONField()),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("available_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="realtimeoutboxevent",
            index=models.Index(
                fields=["delivered_at", "available_at", "created_at"],
                name="realtime_outbox_pending_idx",
            ),
        ),
    ]
