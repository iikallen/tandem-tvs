# Generated for Stage 3.
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("publications", "0002_auditevent_publication_publications_search_idx_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="Comment",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("body", models.TextField(blank=True, max_length=5000)),
                (
                    "status",
                    models.CharField(
                        choices=[("ACTIVE", "Active"), ("DELETED", "Deleted")],
                        default="ACTIVE",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("edited_at", models.DateTimeField(blank=True, null=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="comments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "publication",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comments",
                        to="publications.publication",
                    ),
                ),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.CreateModel(
            name="Reaction",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("reaction_type", models.CharField(choices=[("LIKE", "Like")], max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "publication",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reactions",
                        to="publications.publication",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reactions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="comment",
            index=models.Index(
                fields=["publication", "status", "created_at", "id"], name="comment_pub_page_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="comment",
            index=models.Index(fields=["author", "-created_at"], name="comment_author_idx"),
        ),
        migrations.AddConstraint(
            model_name="comment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("deleted_at__isnull", True), ("status", "ACTIVE")),
                    models.Q(("body", ""), ("deleted_at__isnull", False), ("status", "DELETED")),
                    _connector="OR",
                ),
                name="comment_deleted_shape",
            ),
        ),
        migrations.AddIndex(
            model_name="reaction",
            index=models.Index(
                fields=["publication", "reaction_type"], name="reaction_pub_type_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="reaction",
            index=models.Index(fields=["user", "-created_at"], name="reaction_user_idx"),
        ),
        migrations.AddConstraint(
            model_name="reaction",
            constraint=models.UniqueConstraint(
                fields=("publication", "user", "reaction_type"),
                name="reaction_publication_user_type_unique",
            ),
        ),
    ]
