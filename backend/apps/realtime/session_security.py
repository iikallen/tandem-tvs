import hashlib
import hmac

from django.conf import settings
from django.contrib.sessions.models import Session
from django.utils import timezone

from .claims import RealtimeTicket


def session_fingerprint(session_key: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        session_key.encode(),
        hashlib.sha256,
    ).hexdigest()


def ticket_session_deadline(claims: RealtimeTicket) -> int | None:
    if not claims.session_key or not hmac.compare_digest(
        claims.session_fingerprint,
        session_fingerprint(claims.session_key),
    ):
        return None
    row = Session.objects.filter(
        session_key=claims.session_key,
        expire_date__gt=timezone.now(),
    ).first()
    if row is None:
        return None
    values = row.get_decoded()
    if str(values.get("_auth_user_id", "")) != str(claims.user_id):
        return None
    if int(values.get("security_epoch", 0)) != claims.security_epoch:
        return None
    now = int(timezone.now().timestamp())
    fallback_started = int(row.expire_date.timestamp()) - settings.SESSION_COOKIE_AGE
    started = int(values.get("auth_started_at", fallback_started))
    last_seen = int(values.get("auth_last_seen_at", started))
    deadline = min(
        int(row.expire_date.timestamp()),
        started + settings.AUTH_SESSION_MAX_AGE_SECONDS,
        last_seen + settings.AUTH_SESSION_IDLE_SECONDS,
    )
    return deadline if deadline > now else None
