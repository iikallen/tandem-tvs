from django.contrib.auth.backends import ModelBackend

from .managers import UserManager
from .models import User


class CaseInsensitiveModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        normalized = UserManager.normalize_username(username or kwargs.get("username", ""))
        if not normalized or password is None:
            return None
        try:
            user = User.objects.get(username__iexact=normalized)
        except User.DoesNotExist:
            User().set_password(password)
            return None
        return user if user.check_password(password) and self.user_can_authenticate(user) else None
