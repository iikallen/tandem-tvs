from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("discussions", "0002_commentattachment_commentmention_commentreport_and_more"),
        ("notifications", "0002_migrate_legacy_notifications"),
    ]

    operations = [migrations.DeleteModel(name="Notification")]
