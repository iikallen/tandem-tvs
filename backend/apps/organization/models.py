from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q


class OrgUnit(models.Model):
    external_id = models.CharField(max_length=128, unique=True, editable=False)
    name = models.CharField(max_length=255)
    kind = models.CharField(max_length=64, blank=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "external_id"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(id=F("parent_id")),
                name="organization_orgunit_not_own_parent",
            )
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_external_id = self.external_id

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if self.pk and self.external_id != self._original_external_id:
            raise ValidationError({"external_id": "Portal organization ID is immutable."})
        super().save(*args, **kwargs)
        self._original_external_id = self.external_id
