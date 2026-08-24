from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("identity", "0005_require_local_username")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="security_epoch",
            field=models.PositiveBigIntegerField(default=1),
        ),
        migrations.AddConstraint(
            model_name="accessgrant",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("module", "PLATFORM"), ("role", "ADMIN"))
                    | models.Q(
                        ("module", "NEWS"),
                        ("role__in", ["MEMBER", "AUTHOR", "EDITOR", "MODERATOR", "ADMIN"]),
                    )
                    | models.Q(("module", "MESSENGER"), ("role__in", ["MEMBER", "ADMIN"]))
                ),
                name="identity_access_grant_valid_pair",
            ),
        ),
    ]
