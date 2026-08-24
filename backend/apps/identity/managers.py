import unicodedata
from typing import TYPE_CHECKING

from django.contrib.auth.base_user import BaseUserManager

if TYPE_CHECKING:
    from .models import User


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    @staticmethod
    def normalize_username(username: str) -> str:
        return unicodedata.normalize("NFKC", username).strip().casefold()

    def create_user(self, username: str | None = None, password=None, **extra_fields) -> "User":
        username = username or extra_fields.get("portal_id", "")
        username = self.normalize_username(username)
        if not username:
            raise ValueError("username is required")

        email = extra_fields.get("email", "")
        if email:
            extra_fields["email"] = self.normalize_email(email)

        user = self.model(username=username, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, username: str | None = None, password=None, **extra_fields):
        raise NotImplementedError(
            "Use bootstrap_local_admin; product authorization uses AccessGrant"
        )
