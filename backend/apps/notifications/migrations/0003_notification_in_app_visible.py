from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notifications", "0002_migrate_legacy_notifications")]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="in_app_visible",
            field=models.BooleanField(default=True),
        ),
    ]
