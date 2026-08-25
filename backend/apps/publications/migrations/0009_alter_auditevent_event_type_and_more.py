from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("publications", "0008_local_audience_identity"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("publication.created", "Publication created"),
                    ("publication.updated", "Publication updated"),
                    ("publication.published", "Publication published"),
                    ("publication.transitioned", "Publication transitioned"),
                    ("publication.submitted_for_review", "Publication submitted for review"),
                    ("publication.returned_to_draft", "Publication returned to draft"),
                    ("publication.scheduled", "Publication scheduled"),
                    ("publication.schedule_cancelled", "Publication schedule cancelled"),
                    ("publication.unpublished", "Publication unpublished"),
                    ("publication.archived", "Publication archived"),
                    ("publication.duplicated", "Publication duplicated"),
                    ("publication.pinned", "Publication pinned"),
                    ("publication.unpinned", "Publication unpinned"),
                    ("taxonomy.category.created", "Category created"),
                    ("taxonomy.category.updated", "Category updated"),
                    ("taxonomy.tag.created", "Tag created"),
                    ("taxonomy.tag.updated", "Tag updated"),
                    ("media.uploaded", "Media uploaded"),
                    ("media.deleted", "Media deleted"),
                    ("comment.hidden", "Comment hidden"),
                    ("comment.restored", "Comment restored"),
                    ("comment.removed", "Comment removed"),
                    ("report.resolved", "Report resolved"),
                    ("user.commenting_restricted", "User commenting restricted"),
                    ("restriction.revoked", "Restriction revoked"),
                    ("engagement.settings_updated", "Engagement settings updated"),
                    ("publication.discussion_closed", "Discussion closed"),
                    ("publication.discussion_opened", "Discussion opened"),
                    ("stop_word.created", "Stop word created"),
                    ("stop_word.disabled", "Stop word disabled"),
                    ("publication.acknowledged", "Publication acknowledged"),
                    ("messenger.member.added", "Messenger member added"),
                    ("messenger.member.removed", "Messenger member removed"),
                    ("messenger.member.role_changed", "Messenger member role changed"),
                    ("messenger.message.edited", "Messenger message edited"),
                    ("messenger.message.sent", "Messenger message sent"),
                    ("messenger.message.deleted", "Messenger message deleted"),
                    ("messenger.message.forwarded", "Messenger message forwarded"),
                    ("messenger.reaction.changed", "Messenger reaction changed"),
                    ("messenger.message.pinned", "Messenger message pinned"),
                    ("messenger.message.unpinned", "Messenger message unpinned"),
                ],
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="auditevent",
            name="target_type",
            field=models.CharField(
                choices=[
                    ("publication", "Publication"),
                    ("category", "Category"),
                    ("tag", "Tag"),
                    ("media", "Media"),
                    ("comment", "Comment"),
                    ("report", "Report"),
                    ("user", "User"),
                    ("settings", "Settings"),
                    ("acknowledgement", "Acknowledgement"),
                    ("conversation", "Conversation"),
                    ("message", "Message"),
                ],
                default="publication",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="mediaasset",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING_SCAN", "Pending scan"),
                    ("READY", "Ready"),
                    ("REJECTED", "Rejected"),
                ],
                default="READY",
                max_length=16,
            ),
        ),
    ]
