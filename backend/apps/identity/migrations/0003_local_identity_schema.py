import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("identity", "0002_user_position_group_external_id_and_more")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="username",
            field=models.CharField(max_length=150, null=True),
        ),
        migrations.AlterField(
            model_name="user",
            name="portal_id",
            field=models.CharField(
                blank=True, editable=False, max_length=128, null=True, unique=True
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="activated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="password_changed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="AccessGrant",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "module",
                    models.CharField(
                        choices=[
                            ("PLATFORM", "Platform"),
                            ("NEWS", "News"),
                            ("MESSENGER", "Messenger"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("MEMBER", "Member"),
                            ("AUTHOR", "Author"),
                            ("EDITOR", "Editor"),
                            ("MODERATOR", "Moderator"),
                            ("ADMIN", "Admin"),
                        ],
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_access_grants",
                        to="identity.user",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="access_grants",
                        to="identity.user",
                    ),
                ),
            ],
            options={
                "ordering": ["module", "role", "id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "module", "role"), name="identity_access_grant_unique"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="AccountInvitation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_account_invitations",
                        to="identity.user",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="account_invitations",
                        to="identity.user",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PasswordResetRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_password_resets",
                        to="identity.user",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="password_resets",
                        to="identity.user",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="AuthSecurityEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("event_type", models.CharField(max_length=64)),
                ("username_fingerprint", models.CharField(blank=True, max_length=64)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent_fingerprint", models.CharField(blank=True, max_length=64)),
                ("request_id", models.CharField(blank=True, max_length=128)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="auth_security_events",
                        to="identity.user",
                    ),
                ),
            ],
            options={
                "ordering": ["-occurred_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["event_type", "-occurred_at"], name="auth_event_type_time_idx"
                    ),
                    models.Index(fields=["user", "-occurred_at"], name="auth_event_user_time_idx"),
                ],
            },
        ),
    ]
