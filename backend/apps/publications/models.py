import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.core.exceptions import ValidationError
from django.db import connection, models
from django.db.models import Q
from django.db.models.functions import Cast
from django.utils import timezone

from apps.organization.models import OrgUnit

from .rich_text import (
    empty_rich_text_document,
    rich_text_to_plain_text,
    validate_rich_text_document,
)

MODULE_ROLE_MAX_LENGTH = 64
SEARCH_VECTOR = (
    SearchVector("title", weight="A", config="simple")
    + SearchVector("summary", weight="B", config="simple")
    + SearchVector("body_text", weight="C", config="simple")
)


class PublicationQuerySet(models.QuerySet):
    def visible_to(self, user):
        if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
            return self.none()

        audience = Q(kind="ALL") | Q(kind="EMPLOYEE", employee=user)
        org_unit = getattr(user, "org_unit", None)
        if org_unit is not None and org_unit.is_active:
            audience |= Q(kind="ORG_UNIT", org_unit=org_unit)
        roles = [role for role in getattr(user, "module_roles", []) if isinstance(role, str)]
        if roles:
            audience |= Q(kind="MODULE_ROLE", module_role__in=roles)

        addressed = AudienceRule.objects.filter(audience).values("publication_id")
        return self.filter(
            pk__in=addressed,
            status="PUBLISHED",
            published_at__lte=timezone.now(),
        )

    def search(self, query: str):
        query = query.strip()
        if not query:
            return self.annotate(search_rank=models.Value(0.0))
        if connection.vendor != "postgresql":
            return self.filter(
                Q(title__icontains=query)
                | Q(summary__icontains=query)
                | Q(body_text__icontains=query)
            ).annotate(
                search_rank=models.Value(
                    Decimal("0"),
                    output_field=models.DecimalField(max_digits=12, decimal_places=8),
                )
            )

        search_query = SearchQuery(query, config="simple", search_type="plain")
        return self.annotate(
            search_vector=SEARCH_VECTOR,
            search_rank=Cast(
                SearchRank(SEARCH_VECTOR, search_query),
                models.DecimalField(max_digits=12, decimal_places=8),
            ),
        ).filter(search_vector=search_query)


class PublicationManager(models.Manager["Publication"]):
    def get_queryset(self) -> PublicationQuerySet:
        return PublicationQuerySet(self.model, using=self._db)

    def visible_to(self, user) -> PublicationQuerySet:
        return self.get_queryset().visible_to(user)


class Category(models.Model):
    slug = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=160)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name", "id"]

    def __str__(self) -> str:
        return self.name


class Publication(models.Model):
    if TYPE_CHECKING:
        audience_rules: models.Manager["AudienceRule"]

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, allow_unicode=True)
    summary = models.TextField(max_length=1_000)
    body = models.JSONField(
        default=empty_rich_text_document,
        validators=[validate_rich_text_document],
    )
    body_text = models.TextField(blank=True, editable=False)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="publications")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="authored_publications",
    )
    status = models.CharField(max_length=32, choices=Status, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: ClassVar[PublicationManager] = PublicationManager()  # pyright: ignore[reportIncompatibleVariableOverride]

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["status", "-published_at", "-id"],
                name="publications_feed_idx",
            ),
            GinIndex(SEARCH_VECTOR, name="publications_search_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(status="DRAFT") | models.Q(published_at__isnull=True),
                name="publication_draft_has_no_date",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="PUBLISHED") | models.Q(published_at__isnull=False),
                name="publication_published_has_date",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        self.body_text = rich_text_to_plain_text(self.body)
        if update_fields := kwargs.get("update_fields"):
            if "body" in update_fields:
                kwargs["update_fields"] = {*update_fields, "body_text"}
        super().save(*args, **kwargs)


class AudienceRule(models.Model):
    class Kind(models.TextChoices):
        ALL = "ALL", "All employees"
        ORG_UNIT = "ORG_UNIT", "Organization unit"
        EMPLOYEE = "EMPLOYEE", "Employee"
        MODULE_ROLE = "MODULE_ROLE", "Module role"

    publication = models.ForeignKey(
        Publication,
        on_delete=models.CASCADE,
        related_name="audience_rules",
    )
    kind = models.CharField(max_length=32, choices=Kind)
    org_unit = models.ForeignKey(
        OrgUnit,
        to_field="external_id",
        db_column="org_unit_external_id",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="publication_audience_rules",
    )
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        to_field="portal_id",
        db_column="employee_portal_id",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="publication_audience_rules",
    )
    module_role = models.CharField(max_length=MODULE_ROLE_MAX_LENGTH, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind="ALL",
                        org_unit__isnull=True,
                        employee__isnull=True,
                        module_role="",
                    )
                    | models.Q(
                        kind="ORG_UNIT",
                        org_unit__isnull=False,
                        employee__isnull=True,
                        module_role="",
                    )
                    | models.Q(
                        kind="EMPLOYEE",
                        org_unit__isnull=True,
                        employee__isnull=False,
                        module_role="",
                    )
                    | (
                        models.Q(
                            kind="MODULE_ROLE",
                            org_unit__isnull=True,
                            employee__isnull=True,
                        )
                        & ~models.Q(module_role="")
                    )
                ),
                name="audience_rule_target_shape",
            ),
            models.UniqueConstraint(
                fields=["publication", "kind"],
                condition=models.Q(kind="ALL"),
                name="audience_rule_all_once",
            ),
            models.UniqueConstraint(
                fields=["publication", "org_unit"],
                condition=models.Q(kind="ORG_UNIT"),
                name="audience_rule_org_unique",
            ),
            models.UniqueConstraint(
                fields=["publication", "employee"],
                condition=models.Q(kind="EMPLOYEE"),
                name="audience_rule_employee_unique",
            ),
            models.UniqueConstraint(
                fields=["publication", "module_role"],
                condition=models.Q(kind="MODULE_ROLE"),
                name="audience_rule_role_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.publication.pk}: {self.kind}"


class PublicationView(models.Model):
    publication = models.ForeignKey(
        Publication,
        on_delete=models.CASCADE,
        related_name="views",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="publication_views",
    )
    first_viewed_at = models.DateTimeField()
    last_viewed_at = models.DateTimeField()

    class Meta:
        ordering = ["-last_viewed_at", "-id"]
        indexes = [
            models.Index(
                fields=["user", "-last_viewed_at"],
                name="publication_view_user_idx",
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["publication", "user"],
                name="publication_view_user_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.publication.pk}: {self.user.pk}"


class AuditEvent(models.Model):
    class Type(models.TextChoices):
        CREATED = "publication.created", "Publication created"
        UPDATED = "publication.updated", "Publication updated"
        PUBLISHED = "publication.published", "Publication published"

    publication = models.ForeignKey(
        Publication,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="publication_audit_events",
    )
    event_type = models.CharField(max_length=64, choices=Type)
    previous_state = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["publication", "created_at"], name="publication_audit_idx")]

    def __str__(self) -> str:
        return f"{self.event_type}: {self.publication.pk}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Audit events are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events are append-only.")
