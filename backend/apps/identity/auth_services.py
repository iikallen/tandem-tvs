import hashlib
import hmac
import ipaddress
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .managers import UserManager
from .models import (
    AccessGrant,
    AccountInvitation,
    AuthSecurityEvent,
    PasswordResetRequest,
    User,
)
from .permissions import access_grants


def fingerprint(value: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def request_ip(request) -> str | None:
    for key in ("HTTP_X_TANDEM_CLIENT_IP", "REMOTE_ADDR"):
        value = request.META.get(key, "").strip()
        try:
            return ipaddress.ip_address(value).compressed
        except ValueError:
            continue
    return None


def record_auth_event(request, event_type: str, *, user=None, username="", metadata=None) -> None:
    AuthSecurityEvent.objects.create(
        event_type=event_type,
        user=user,
        username_fingerprint=fingerprint(UserManager.normalize_username(username))
        if username
        else "",
        ip_address=request_ip(request),
        user_agent_fingerprint=fingerprint(request.META.get("HTTP_USER_AGENT", ""))
        if request.META.get("HTTP_USER_AGENT")
        else "",
        request_id=request.META.get("HTTP_X_REQUEST_ID", "")[:128],
        metadata=metadata or {},
    )


def login_is_limited(username: str, ip: str | None) -> bool:
    username_key = f"auth:login:user:{fingerprint(UserManager.normalize_username(username))}"
    ip_key = f"auth:login:ip:{fingerprint(ip or 'unknown')}"
    return int(cache.get(username_key, 0)) >= 5 or int(cache.get(ip_key, 0)) >= 20


def record_login_failure(username: str, ip: str | None) -> None:
    for key in (
        f"auth:login:user:{fingerprint(UserManager.normalize_username(username))}",
        f"auth:login:ip:{fingerprint(ip or 'unknown')}",
    ):
        if not cache.add(key, 1, timeout=300):
            cache.incr(key)


def access_payload(user: User) -> dict[str, list[str]]:
    payload = {"platform": [], "news": [], "messenger": []}
    for item in access_grants(user):
        payload[item.module.casefold()].append(item.role)
    return {key: sorted(values) for key, values in payload.items()}


def _increment_window(key: str) -> int:
    if cache.add(key, 1, timeout=settings.AUTH_RESET_WINDOW_SECONDS):
        return 1
    try:
        return int(cache.incr(key))
    except ValueError:
        if cache.add(key, 1, timeout=settings.AUTH_RESET_WINDOW_SECONDS):
            return 1
        return int(cache.incr(key))


def reserve_password_reset(email: str, ip: str | None) -> bool:
    """Reserve one generic recovery attempt without looking up the account."""
    account_count = _increment_window(f"auth:reset:account:{fingerprint(email.strip().casefold())}")
    ip_count = _increment_window(f"auth:reset:ip:{fingerprint(ip or 'unknown')}")
    return (
        account_count <= settings.AUTH_RESET_ACCOUNT_LIMIT
        and ip_count <= settings.AUTH_RESET_IP_LIMIT
    )


def bump_security_epoch(user: User) -> int:
    User.objects.filter(pk=user.pk).update(security_epoch=F("security_epoch") + 1)
    user.refresh_from_db(fields=["security_epoch"])
    from apps.realtime.events import invalidate_user_after_commit

    invalidate_user_after_commit(user.pk)
    return user.security_epoch


def validate_local_password(password: str, user: User | None = None) -> None:
    if len(password) > 128:
        raise ValidationError("Password must contain at most 128 characters.")
    validate_password(password, user=user)


def _new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hashlib.sha256(token.encode()).hexdigest()


@transaction.atomic
def issue_invitation(
    user: User, *, actor: User, ttl_hours: int = 48
) -> tuple[AccountInvitation, str]:
    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.is_active or user.activated_at is not None or user.has_usable_password():
        raise ValidationError("Invitation is only available for an unactivated account.")
    now = timezone.now()
    AccountInvitation.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
    token, token_hash = _new_token()
    row = AccountInvitation.objects.create(
        user=user,
        token_hash=token_hash,
        created_by=actor,
        expires_at=now + timedelta(hours=ttl_hours),
    )
    return row, token


@transaction.atomic
def activate_account(token: str, password: str) -> User:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    invitation = (
        AccountInvitation.objects.select_for_update()
        .select_related("user")
        .filter(token_hash=token_hash)
        .first()
    )
    now = timezone.now()
    if invitation is None or invitation.used_at is not None or invitation.expires_at <= now:
        raise ValidationError("Invitation is invalid or expired.")
    user = invitation.user
    if not user.is_active:
        raise ValidationError("Account is disabled.")
    validate_local_password(password, user)
    user.set_password(password)
    user.activated_at = now
    user.password_changed_at = now
    user.save(update_fields=["password", "activated_at", "password_changed_at", "updated_at"])
    invitation.used_at = now
    invitation.save(update_fields=["used_at"])
    return user


@transaction.atomic
def issue_password_reset(
    user: User, *, actor: User | None = None, ttl_minutes: int = 30
) -> tuple[PasswordResetRequest, str]:
    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.is_active or user.activated_at is None or not user.has_usable_password():
        raise ValidationError("Password reset is only available for an activated account.")
    now = timezone.now()
    PasswordResetRequest.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
    token, token_hash = _new_token()
    row = PasswordResetRequest.objects.create(
        user=user,
        token_hash=token_hash,
        created_by=actor,
        expires_at=now + timedelta(minutes=ttl_minutes),
    )
    return row, token


@transaction.atomic
def reset_password(token: str, password: str) -> User:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    reset = (
        PasswordResetRequest.objects.select_for_update()
        .select_related("user")
        .filter(token_hash=token_hash)
        .first()
    )
    now = timezone.now()
    if reset is None or reset.used_at is not None or reset.expires_at <= now:
        raise ValidationError("Reset token is invalid or expired.")
    user = reset.user
    if not user.is_active:
        raise ValidationError("Account is disabled.")
    validate_local_password(password, user)
    user.set_password(password)
    user.password_changed_at = now
    user.activated_at = user.activated_at or now
    user.save(update_fields=["password", "password_changed_at", "activated_at", "updated_at"])
    reset.used_at = now
    reset.save(update_fields=["used_at"])
    bump_security_epoch(user)
    return user


@transaction.atomic
def grant(user: User, module: str, role: str, *, actor: User) -> tuple[AccessGrant, bool]:
    row, created = AccessGrant.objects.get_or_create(
        user=user, module=module, role=role, defaults={"created_by": actor}
    )
    if created:
        bump_security_epoch(user)
    return row, created


@transaction.atomic
def revoke_grant(user: User, module: str, role: str) -> bool:
    deleted, _ = AccessGrant.objects.filter(user=user, module=module, role=role).delete()
    if deleted:
        bump_security_epoch(user)
    return bool(deleted)
