import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.core.exceptions import ValidationError
from django.db import connection, models
from django.db.models import Q
from django.db.models.functions import Cast, Concat
from django.utils import timezone

from apps.organization.models import OrgUnit

from .rich_text import (
    empty_rich_text_document,
    rich_text_to_plain_text,
    validate_rich_text_document,
)

MODULE_ROLE_MAX_LENGTH = 64
POSITION_GROUP_MAX_LENGTH = 128
MAX_PINNED = 5


def media_storage_path(instance: "MediaAsset", _filename: str) -> str:
    return instance.storage_key


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
            audience |= Q(kind="ORG_UNIT", org_unit=org_unit, org_unit__is_active=True)
            ancestor_ids: list[str] = []
            current = org_unit.parent
            seen: set[int] = set()
            while current is not None and current.pk not in seen:
                seen.add(current.pk)
                if current.is_active:
                    ancestor_ids.append(current.external_id)
                current = current.parent
            if ancestor_ids:
                audience |= Q(
                    kind="ORG_UNIT",
                    org_unit_id__in=ancestor_ids,
                    org_unit__is_active=True,
                    include_descendants=True,
                )
        roles = [role for role in getattr(user, "module_roles", []) if isinstance(role, str)]
        if roles:
            audience |= Q(kind="MODULE_ROLE", module_role__in=roles)
        position_group_id = getattr(user, "position_group_external_id", "")
        if position_group_id:
            audience |= Q(
                kind="POSITION_GROUP",
                position_group_external_id=position_group_id,
            )

        addressed = AudienceRule.objects.filter(audience).values("publication_id")
        now = timezone.now()
        return self.filter(
            pk__in=addressed,
            status="PUBLISHED",
            published_at__lte=now,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))

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
                ),
                search_cursor=Cast("id", output_field=models.CharField()),
            )

        search_query = SearchQuery(query, config="simple", search_type="plain")
        ranked = self.annotate(
            search_vector=SEARCH_VECTOR,
            search_rank=Cast(
                SearchRank(SEARCH_VECTOR, search_query),
                models.DecimalField(max_digits=12, decimal_places=8),
            ),
        ).filter(search_vector=search_query)
        return ranked.annotate(
            search_cursor=Concat(
                models.Func(
                    models.F("search_rank"),
                    models.Value("FM0000000000.00000000"),
                    function="to_char",
                    output_field=models.CharField(),
                ),
                models.Value(":"),
                Cast("id", output_field=models.CharField()),
            )
        )


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
    comment_attachments_enabled = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order", "name", "id"]

    def __str__(self) -> str:
        return self.name


class Tag(models.Model):
    slug = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=160)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name


class Publication(models.Model):
    if TYPE_CHECKING:
        audience_rules: models.Manager["AudienceRule"]
        audit_events: models.Manager["AuditEvent"]
        media_usages: models.Manager["MediaUsage"]
        versions: models.Manager["PublicationVersion"]

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        IN_REVIEW = "IN_REVIEW", "In review"
        SCHEDULED = "SCHEDULED", "Scheduled"
        PUBLISHED = "PUBLISHED", "Published"
        UNPUBLISHED = "UNPUBLISHED", "Unpublished"
        ARCHIVED = "ARCHIVED", "Archived"

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
    tags = models.ManyToManyField(Tag, blank=True, related_name="publications")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="authored_publications",
    )
    status = models.CharField(max_length=32, choices=Status, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    unpublished_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    edit_revision = models.PositiveIntegerField(default=0)
    last_autosaved_at = models.DateTimeField(null=True, blank=True)
    cover = models.ForeignKey(
        "MediaAsset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cover_publications",
    )
    comments_enabled = models.BooleanField(default=True)
    reactions_enabled = models.BooleanField(default=True)
    acknowledgement_required = models.BooleanField(default=False)
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
                condition=(
                    ~models.Q(status__in=["DRAFT", "IN_REVIEW", "SCHEDULED"])
                    | models.Q(published_at__isnull=True)
                ),
                name="publication_prepublication_has_no_date",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="PUBLISHED") | models.Q(published_at__isnull=False),
                name="publication_published_has_date",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="SCHEDULED") | models.Q(scheduled_for__isnull=False),
                name="publication_scheduled_has_date",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="ARCHIVED") | models.Q(archived_at__isnull=False),
                name="publication_archived_has_date",
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
        POSITION_GROUP = "POSITION_GROUP", "Position group"

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
    include_descendants = models.BooleanField(default=False)
    position_group_external_id = models.CharField(max_length=POSITION_GROUP_MAX_LENGTH, blank=True)
    position_group_name = models.CharField(max_length=255, blank=True)

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
            models.UniqueConstraint(
                fields=["publication", "position_group_external_id"],
                condition=models.Q(kind="POSITION_GROUP"),
                name="audience_rule_position_group_unique",
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


class PublicationRecipient(models.Model):
    """Portal identity snapshot used as the exact analytics/ack denominator."""

    publication = models.ForeignKey(
        Publication, on_delete=models.PROTECT, related_name="recipient_snapshots"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="publication_recipients"
    )
    portal_id = models.CharField(max_length=128)
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    org_unit_external_id = models.CharField(max_length=128, blank=True)
    org_unit_name = models.CharField(max_length=255, blank=True)
    is_current = models.BooleanField(default=True)
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name", "portal_id"]
        indexes = [
            models.Index(fields=["publication", "is_current"], name="pub_recipient_current_idx"),
            models.Index(fields=["publication", "portal_id"], name="pub_recipient_portal_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["publication", "portal_id"], name="pub_recipient_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.publication.pk}: {self.portal_id}"


class AcknowledgementQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Acknowledgements are append-only.")

    def delete(self):
        raise ValidationError("Acknowledgements are append-only.")


class AcknowledgementManager(models.Manager["Acknowledgement"]):
    def get_queryset(self) -> AcknowledgementQuerySet:
        return AcknowledgementQuerySet(self.model, using=self._db)


class Acknowledgement(models.Model):
    publication = models.ForeignKey(
        Publication, on_delete=models.PROTECT, related_name="acknowledgements"
    )
    recipient = models.OneToOneField(
        PublicationRecipient, on_delete=models.PROTECT, related_name="acknowledgement"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="acknowledgements"
    )
    acknowledged_at = models.DateTimeField(auto_now_add=True)

    objects = AcknowledgementManager()

    class Meta:
        ordering = ["acknowledged_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["publication", "user"], name="publication_ack_user_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.publication.pk}: {self.user.pk}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Acknowledgements are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Acknowledgements are append-only.")


class AuditEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Audit events are append-only.")

    def delete(self):
        raise ValidationError("Audit events are append-only.")


class AuditEventManager(models.Manager["AuditEvent"]):
    def get_queryset(self) -> AuditEventQuerySet:
        return AuditEventQuerySet(self.model, using=self._db)


class AuditEvent(models.Model):
    class TargetType(models.TextChoices):
        PUBLICATION = "publication", "Publication"
        CATEGORY = "category", "Category"
        TAG = "tag", "Tag"
        MEDIA = "media", "Media"
        COMMENT = "comment", "Comment"
        REPORT = "report", "Report"
        USER = "user", "User"
        SETTINGS = "settings", "Settings"
        ACKNOWLEDGEMENT = "acknowledgement", "Acknowledgement"

    class Type(models.TextChoices):
        CREATED = "publication.created", "Publication created"
        UPDATED = "publication.updated", "Publication updated"
        PUBLISHED = "publication.published", "Publication published"
        TRANSITIONED = "publication.transitioned", "Publication transitioned"
        SUBMITTED_FOR_REVIEW = (
            "publication.submitted_for_review",
            "Publication submitted for review",
        )
        RETURNED_TO_DRAFT = "publication.returned_to_draft", "Publication returned to draft"
        SCHEDULED = "publication.scheduled", "Publication scheduled"
        SCHEDULE_CANCELLED = "publication.schedule_cancelled", "Publication schedule cancelled"
        UNPUBLISHED = "publication.unpublished", "Publication unpublished"
        ARCHIVED = "publication.archived", "Publication archived"
        DUPLICATED = "publication.duplicated", "Publication duplicated"
        PINNED = "publication.pinned", "Publication pinned"
        UNPINNED = "publication.unpinned", "Publication unpinned"
        CATEGORY_CREATED = "taxonomy.category.created", "Category created"
        CATEGORY_UPDATED = "taxonomy.category.updated", "Category updated"
        TAG_CREATED = "taxonomy.tag.created", "Tag created"
        TAG_UPDATED = "taxonomy.tag.updated", "Tag updated"
        MEDIA_UPLOADED = "media.uploaded", "Media uploaded"
        MEDIA_DELETED = "media.deleted", "Media deleted"
        COMMENT_HIDDEN = "comment.hidden", "Comment hidden"
        COMMENT_RESTORED = "comment.restored", "Comment restored"
        COMMENT_REMOVED = "comment.removed", "Comment removed"
        REPORT_RESOLVED = "report.resolved", "Report resolved"
        USER_RESTRICTED = "user.commenting_restricted", "User commenting restricted"
        RESTRICTION_REVOKED = "restriction.revoked", "Restriction revoked"
        ENGAGEMENT_UPDATED = "engagement.settings_updated", "Engagement settings updated"
        DISCUSSION_CLOSED = "publication.discussion_closed", "Discussion closed"
        DISCUSSION_OPENED = "publication.discussion_opened", "Discussion opened"
        STOP_WORD_CREATED = "stop_word.created", "Stop word created"
        STOP_WORD_DISABLED = "stop_word.disabled", "Stop word disabled"
        ACKNOWLEDGED = "publication.acknowledged", "Publication acknowledged"

    publication = models.ForeignKey(
        Publication,
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="publication_audit_events",
    )
    event_type = models.CharField(max_length=64, choices=Type)
    target_type = models.CharField(
        max_length=32,
        choices=TargetType,
        default=TargetType.PUBLICATION,
    )
    target_id = models.CharField(max_length=255, blank=True)
    previous_state = models.JSONField(default=dict)
    new_state = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AuditEventManager()

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["publication", "created_at"], name="publication_audit_idx"),
            models.Index(
                fields=["target_type", "target_id", "created_at"],
                name="module_audit_target_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_type}: {self.target_type}/{self.target_id}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Audit events are append-only.")
        publication_id = getattr(self, "publication_id", None)
        if publication_id and not self.target_id:
            self.target_type = self.TargetType.PUBLICATION
            self.target_id = str(publication_id)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events are append-only.")


class PublicationVersionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Publication versions are append-only.")

    def delete(self):
        raise ValidationError("Publication versions are append-only.")


class PublicationVersionManager(models.Manager["PublicationVersion"]):
    def get_queryset(self) -> PublicationVersionQuerySet:
        return PublicationVersionQuerySet(self.model, using=self._db)


class PublicationVersion(models.Model):
    publication = models.ForeignKey(Publication, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="publication_versions",
    )
    reason = models.CharField(max_length=64)
    snapshot = models.JSONField()
    changed_fields = models.JSONField(default=list)
    content_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PublicationVersionManager()

    class Meta:
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["publication", "version_number"],
                name="publication_version_number_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.publication.pk} v{self.version_number}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Publication versions are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Publication versions are append-only.")


class PublicationPin(models.Model):
    publication = models.OneToOneField(Publication, on_delete=models.CASCADE, related_name="pin")
    slot = models.PositiveSmallIntegerField(unique=True)
    pinned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="publication_pins",
    )
    pinned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["slot"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(slot__gte=1, slot__lte=MAX_PINNED),
                name="publication_pin_slot_range",
            )
        ]

    def __str__(self) -> str:
        return f"slot {self.slot}: {self.publication.pk}"


class MediaAsset(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "IMAGE", "Image"
        VIDEO = "VIDEO", "Video"
        DOCUMENT = "DOCUMENT", "Document"

    class Status(models.TextChoices):
        READY = "READY", "Ready"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_name = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=255, unique=True, editable=False)
    file = models.FileField(upload_to=media_storage_path, max_length=255)
    mime_type = models.CharField(max_length=128)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)
    kind = models.CharField(max_length=16, choices=Kind)
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_media_assets",
    )
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status, default=Status.READY)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.original_name


class MediaUsage(models.Model):
    class Purpose(models.TextChoices):
        COVER = "COVER", "Cover"
        BODY = "BODY", "Body"
        ATTACHMENT = "ATTACHMENT", "Attachment"

    asset = models.ForeignKey(MediaAsset, on_delete=models.PROTECT, related_name="usages")
    publication = models.ForeignKey(
        Publication, on_delete=models.CASCADE, related_name="media_usages"
    )
    purpose = models.CharField(max_length=16, choices=Purpose)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "publication", "purpose"],
                name="media_usage_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.publication.pk}: {self.asset.pk} ({self.purpose})"
