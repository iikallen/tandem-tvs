from django.conf import settings
from django.contrib.auth import logout
from django.utils import timezone


class AuthSessionExpiryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            now = int(timezone.now().timestamp())
            started = int(request.session.get("auth_started_at", now))
            last_seen = int(request.session.get("auth_last_seen_at", now))
            if (
                now - started > settings.AUTH_SESSION_MAX_AGE_SECONDS
                or now - last_seen > settings.AUTH_SESSION_IDLE_SECONDS
            ):
                logout(request)
            else:
                request.session["auth_started_at"] = started
                request.session["auth_last_seen_at"] = now
        return self.get_response(request)
