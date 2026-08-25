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
            session_epoch = int(request.session.get("security_epoch", 0))
            if (
                session_epoch != request.user.security_epoch
                or not request.user.is_active
                or now - started > settings.AUTH_SESSION_MAX_AGE_SECONDS
                or now - last_seen > settings.AUTH_SESSION_IDLE_SECONDS
            ):
                session_key = request.session.session_key
                logout(request)
                if session_key:
                    from apps.realtime.events import invalidate_session
                    from apps.realtime.session_security import session_fingerprint

                    invalidate_session(session_fingerprint(session_key))
            else:
                if "auth_started_at" not in request.session:
                    request.session["auth_started_at"] = started
                if now - last_seen >= settings.AUTH_SESSION_ACTIVITY_CHECKPOINT_SECONDS:
                    request.session["auth_last_seen_at"] = now
        return self.get_response(request)
