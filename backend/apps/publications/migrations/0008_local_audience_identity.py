import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_local_employee(apps, schema_editor):
    AudienceRule = apps.get_model("publications", "AudienceRule")
    User = apps.get_model("identity", "User")
    users = dict(User.objects.exclude(portal_id__isnull=True).values_list("portal_id", "pk"))
    for rule in AudienceRule.objects.exclude(employee_id__isnull=True).iterator():
        rule.employee_local_id = users[rule.employee_id]
        rule.save(update_fields=["employee_local"])


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0006_security_epoch_and_grant_constraint"),
        ("publications", "0007_local_recipient_identity"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="audiencerule", name="audience_rule_target_shape"),
        migrations.RemoveConstraint(
            model_name="audiencerule", name="audience_rule_employee_unique"
        ),
        migrations.AddField(
            model_name="audiencerule",
            name="employee_local",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_local_employee, migrations.RunPython.noop),
        migrations.RemoveField(model_name="audiencerule", name="employee"),
        migrations.RenameField(
            model_name="audiencerule", old_name="employee_local", new_name="employee"
        ),
        migrations.AlterField(
            model_name="audiencerule",
            name="employee",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="publication_audience_rules",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="audiencerule",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        kind="ALL",
                        org_unit__isnull=True,
                        employee__isnull=True,
                        module_role="",
                        position_group_external_id="",
                        position_group_name="",
                        include_descendants=False,
                    )
                    | models.Q(
                        kind="ORG_UNIT",
                        org_unit__isnull=False,
                        employee__isnull=True,
                        module_role="",
                        position_group_external_id="",
                        position_group_name="",
                    )
                    | models.Q(
                        kind="EMPLOYEE",
                        org_unit__isnull=True,
                        employee__isnull=False,
                        module_role="",
                        position_group_external_id="",
                        position_group_name="",
                        include_descendants=False,
                    )
                    | (
                        models.Q(
                            kind="MODULE_ROLE",
                            org_unit__isnull=True,
                            employee__isnull=True,
                            position_group_external_id="",
                            position_group_name="",
                            include_descendants=False,
                        )
                        & ~models.Q(module_role="")
                    )
                    | (
                        models.Q(
                            kind="POSITION_GROUP",
                            org_unit__isnull=True,
                            employee__isnull=True,
                            module_role="",
                            include_descendants=False,
                        )
                        & ~models.Q(position_group_external_id="")
                        & ~models.Q(position_group_name="")
                    )
                ),
                name="audience_rule_target_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="audiencerule",
            constraint=models.UniqueConstraint(
                fields=("publication", "employee"),
                condition=models.Q(("kind", "EMPLOYEE")),
                name="audience_rule_employee_unique",
            ),
        ),
    ]
