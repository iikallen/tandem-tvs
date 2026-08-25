from typing import ClassVar

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from apps.organization.models import OrgUnit

from .managers import UserManager


class User(AbstractBaseUser):
    username = models.CharField(max_length=150, unique=True)
    portal_id = models.CharField(max_length=128, unique=True, null=True, blank=True, editable=False)
    email = models.EmailField(blank=True)
    full_name = models.CharField(max_length=255)
    job_title = models.CharField(max_length=255, blank=True)
    position_group_external_id = models.CharField(max_length=128, blank=True)
    position_group_name = models.CharField(max_length=255, blank=True)
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
    security_epoch = models.PositiveBigIntegerField(default=1)
    activated_at = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    last_portal_sync_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        ordering = ["full_name", "username"]
        indexes = [
            GinIndex(fields=["full_name"], name="user_name_trgm_idx", opclasses=["gin_trgm_ops"]),
            GinIndex(fields=["job_title"], name="user_job_trgm_idx", opclasses=["gin_trgm_ops"]),
        ]
        constraints = [
            models.UniqueConstraint(Lower("username"), name="identity_username_ci_unique"),
            models.UniqueConstraint(
                Lower("email"),
                condition=~models.Q(email=""),
                name="identity_email_ci_unique",
            ),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_portal_id = self.portal_id

    def __str__(self) -> str:
        return self.full_name

    def save(self, *args, **kwargs):
        if self.pk and self.portal_id != self._original_portal_id:
            raise ValidationError({"portal_id": "Portal identity is immutable."})
        if not self.username and self.portal_id:
            self.username = self.portal_id
        self.username = UserManager.normalize_username(self.username)
        self.email = self.email.strip().casefold()
        super().save(*args, **kwargs)
        self._original_portal_id = self.portal_id


class AccessGrant(models.Model):
    class Module(models.TextChoices):
        PLATFORM = "PLATFORM", "Platform"
        NEWS = "NEWS", "News"
        MESSENGER = "MESSENGER", "Messenger"

    class Role(models.TextChoices):
        MEMBER = "MEMBER", "Member"
        AUTHOR = "AUTHOR", "Author"
        EDITOR = "EDITOR", "Editor"
        MODERATOR = "MODERATOR", "Moderator"
        ADMIN = "ADMIN", "Admin"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="access_grants")
    module = models.CharField(max_length=16, choices=Module)
    role = models.CharField(max_length=16, choices=Role)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_access_grants",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["module", "role", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "module", "role"], name="identity_access_grant_unique"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(module="PLATFORM", role="ADMIN")
                    | models.Q(
                        module="NEWS",
                        role__in=["MEMBER", "AUTHOR", "EDITOR", "MODERATOR", "ADMIN"],
                    )
                    | models.Q(module="MESSENGER", role__in=["MEMBER", "ADMIN"])
                ),
                name="identity_access_grant_valid_pair",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user.username}: {self.module}/{self.role}"


class AccountInvitation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="account_invitations")
    token_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_account_invitations"
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Invitation for {self.user.username}"


class PasswordResetRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_resets")
    token_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_password_resets",
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Password reset for {self.user.username}"


class AuthSecurityEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Authentication security events are append-only.")

    def delete(self):
        raise ValidationError("Authentication security events are append-only.")


class AuthSecurityEvent(models.Model):
    event_type = models.CharField(max_length=64)
    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="auth_security_events"
    )
    username_fingerprint = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent_fingerprint = models.CharField(max_length=64, blank=True)
    request_id = models.CharField(max_length=128, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    objects = AuthSecurityEventQuerySet.as_manager()

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["event_type", "-occurred_at"], name="auth_event_type_time_idx"),
            models.Index(fields=["user", "-occurred_at"], name="auth_event_user_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} at {self.occurred_at}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Authentication security events are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Authentication security events are append-only.")
