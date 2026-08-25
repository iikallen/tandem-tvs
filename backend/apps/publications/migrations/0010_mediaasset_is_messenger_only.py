from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("publications", "0009_alter_auditevent_event_type_and_more")]

    operations = [
        migrations.AddField(
            model_name="mediaasset",
            name="is_messenger_only",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
