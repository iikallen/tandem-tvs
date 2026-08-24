from collections import defaultdict

from django.db import migrations, models
from django.db.models.functions import Lower


def normalize_recovery_emails(apps, schema_editor):
    User = apps.get_model("identity", "User")
    grouped: dict[str, list[int]] = defaultdict(list)
    for user_id, email in User.objects.exclude(email="").values_list("id", "email"):
        grouped[email.strip().casefold()].append(user_id)
    duplicates = {email: ids for email, ids in grouped.items() if len(ids) > 1}
    if duplicates:
        raise RuntimeError(
            f"Duplicate recovery emails must be resolved before migration: {duplicates}"
        )
    for email, user_ids in grouped.items():
        User.objects.filter(pk=user_ids[0]).update(email=email)


class Migration(migrations.Migration):
    dependencies = [("identity", "0006_security_epoch_and_grant_constraint")]

    operations = [
        migrations.RunPython(
            normalize_recovery_emails,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                Lower("email"),
                condition=~models.Q(email=""),
                name="identity_email_ci_unique",
            ),
        ),
    ]
