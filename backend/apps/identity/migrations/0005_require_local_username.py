from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [("identity", "0004_backfill_local_identity")]
    operations = [
        migrations.AlterField(
            model_name="user",
            name="username",
            field=models.CharField(max_length=150, unique=True),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                Lower("username"), name="identity_username_ci_unique"
            ),
        ),
        migrations.AlterModelOptions(name="user", options={"ordering": ["full_name", "username"]}),
    ]
