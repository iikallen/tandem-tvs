import hashlib
import json

import django.contrib.postgres.indexes
import django.contrib.postgres.search
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def backfill_stage8_fields(apps, schema_editor):
    Conversation = apps.get_model("messenger", "Conversation")
    Membership = apps.get_model("messenger", "ConversationMembership")
    Message = apps.get_model("messenger", "Message")
    Conversation.objects.filter(last_message_at__isnull=False).update(
        activity_at=models.F("last_message_at")
    )
    Membership.objects.update(
        last_delivered_sequence=models.F("last_read_sequence"),
        delivered_at=models.F("read_at"),
    )
    for message in Message.objects.only("pk", "body").iterator(chunk_size=500):
        canonical = json.dumps(
            {
                "attachment_ids": [],
                "body": message.body,
                "forward_message_id": None,
                "reply_to_id": None,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        message.request_fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
        message.save(update_fields=["request_fingerprint"])


class Migration(migrations.Migration):
    dependencies = [
        ("messenger", "0001_initial"),
        ("publications", "0009_alter_auditevent_event_type_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MessageAttachment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="MessageReaction",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "reaction_type",
                    models.CharField(
                        choices=[
                            ("LIKE", "Like"),
                            ("LOVE", "Love"),
                            ("LAUGH", "Laugh"),
                            ("WOW", "Wow"),
                            ("SAD", "Sad"),
                        ],
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="MessageRevision",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("body", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.CreateModel(
            name="PinnedMessage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("pinned_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-pinned_at", "-id"],
            },
        ),
        migrations.AlterModelOptions(
            name="conversation",
            options={"ordering": ["-activity_at", "-id"]},
        ),
        migrations.RemoveConstraint(
            model_name="conversationmembership",
            name="messenger_membership_unique",
        ),
        migrations.AddField(
            model_name="conversation",
            name="activity_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name="conversationmembership",
            name="delivered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="conversationmembership",
            name="draft_body",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="conversationmembership",
            name="draft_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="conversationmembership",
            name="is_archived",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="conversationmembership",
            name="joined_sequence",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="conversationmembership",
            name="last_delivered_sequence",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="conversationmembership",
            name="left_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="conversationmembership",
            name="left_sequence",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="conversationmembership",
            name="muted_until",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="conversationmembership",
            name="pinned_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="message",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="message",
            name="edited_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="message",
            name="forwarded_snapshot",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="message",
            name="reply_to",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="replies",
                to="messenger.message",
            ),
        ),
        migrations.AddField(
            model_name="message",
            name="request_fingerprint",
            field=models.CharField(max_length=64, null=True),
        ),
        migrations.RunPython(backfill_stage8_fields, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="message",
            name="request_fingerprint",
            field=models.CharField(max_length=64),
        ),
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(fields=["-activity_at", "-id"], name="messenger_activity_idx"),
        ),
        migrations.AddIndex(
            model_name="message",
            index=django.contrib.postgres.indexes.GinIndex(
                django.contrib.postgres.search.SearchVector("body", config="simple"),
                name="messenger_message_fts_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="conversationmembership",
            constraint=models.UniqueConstraint(
                condition=models.Q(("left_at__isnull", True)),
                fields=("conversation", "user"),
                name="messenger_active_membership_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="conversationmembership",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("left_at__isnull", True), ("left_sequence__isnull", True)),
                    models.Q(("left_at__isnull", False), ("left_sequence__isnull", False)),
                    _connector="OR",
                ),
                name="messenger_membership_left_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="conversationmembership",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("left_sequence__isnull", True),
                    ("left_sequence__gte", models.F("joined_sequence")),
                    _connector="OR",
                ),
                name="messenger_membership_sequence_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="conversationmembership",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("last_delivered_sequence__gte", models.F("last_read_sequence"))
                ),
                name="messenger_delivery_covers_read",
            ),
        ),
        migrations.AddField(
            model_name="messageattachment",
            name="asset",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="messenger_attachments",
                to="publications.mediaasset",
            ),
        ),
        migrations.AddField(
            model_name="messageattachment",
            name="message",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="attachments",
                to="messenger.message",
            ),
        ),
        migrations.AddField(
            model_name="messagereaction",
            name="message",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reactions",
                to="messenger.message",
            ),
        ),
        migrations.AddField(
            model_name="messagereaction",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="messenger_message_reactions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="messagerevision",
            name="edited_by",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="messenger_message_revisions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="messagerevision",
            name="message",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="revisions",
                to="messenger.message",
            ),
        ),
        migrations.AddField(
            model_name="pinnedmessage",
            name="conversation",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pinned_messages",
                to="messenger.conversation",
            ),
        ),
        migrations.AddField(
            model_name="pinnedmessage",
            name="message",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pins",
                to="messenger.message",
            ),
        ),
        migrations.AddField(
            model_name="pinnedmessage",
            name="pinned_by",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="messenger_pins",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="messageattachment",
            constraint=models.UniqueConstraint(
                fields=("message", "asset"), name="messenger_message_asset_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="messagereaction",
            constraint=models.UniqueConstraint(
                fields=("message", "user"), name="messenger_reaction_user_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="pinnedmessage",
            constraint=models.UniqueConstraint(
                fields=("conversation", "message"), name="messenger_pinned_message_unique"
            ),
        ),
    ]
