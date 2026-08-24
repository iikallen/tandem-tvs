from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("publications", "0006_category_comment_attachments_enabled_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="publicationrecipient",
            name="pub_recipient_unique",
        ),
        migrations.AlterField(
            model_name="publicationrecipient",
            name="portal_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddConstraint(
            model_name="publicationrecipient",
            constraint=models.UniqueConstraint(
                fields=("publication", "user"),
                name="pub_recipient_user_unique",
            ),
        ),
    ]
