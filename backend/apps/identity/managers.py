from typing import TYPE_CHECKING

from django.contrib.auth.base_user import BaseUserManager

if TYPE_CHECKING:
    from .models import User


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def create_user(self, portal_id: str, password=None, **extra_fields) -> "User":
        if not portal_id:
            raise ValueError("portal_id is required")
        if password:
            raise ValueError("Portal users cannot have a local password")

        email = extra_fields.get("email", "")
        if email:
            extra_fields["email"] = self.normalize_email(email)

        user = self.model(portal_id=portal_id, **extra_fields)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, portal_id: str, password=None, **extra_fields):
        raise NotImplementedError("Local superusers are disabled; roles come from the portal")
