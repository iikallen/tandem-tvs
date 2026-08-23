from typing import ClassVar

from django.contrib.auth.base_user import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import models

from apps.organization.models import OrgUnit

from .managers import UserManager


class User(AbstractBaseUser):
    portal_id = models.CharField(max_length=128, unique=True, editable=False)
    email = models.EmailField(blank=True)
    full_name = models.CharField(max_length=255)
    job_title = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=64, blank=True)
    avatar_url = models.URLField(max_length=2048, blank=True)
    org_unit = models.ForeignKey(
        OrgUnit,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employees",
    )
    module_roles = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    last_portal_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "portal_id"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        ordering = ["full_name", "portal_id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_portal_id = self.portal_id

    def __str__(self) -> str:
        return self.full_name

    def save(self, *args, **kwargs):
        if self.pk and self.portal_id != self._original_portal_id:
            raise ValidationError({"portal_id": "Portal identity is immutable."})
        if self.has_usable_password():
            self.set_unusable_password()
        super().save(*args, **kwargs)
        self._original_portal_id = self.portal_id
