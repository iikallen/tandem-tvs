from celery import shared_task
from django.conf import settings

from .auth_services import issue_password_reset
from .delivery import SMTPAuthDelivery
from .models import User


@shared_task(name="identity.deliver-password-reset")
def deliver_password_reset_task(email: str) -> None:
    if settings.AUTH_RECOVERY_MODE != "SMTP":
        return
    user = (
        User.objects.filter(email__iexact=email, is_active=True, activated_at__isnull=False)
        .order_by("pk")
        .first()
    )
    if user is None:
        return
    _row, token = issue_password_reset(user)
    SMTPAuthDelivery().deliver(
        recipient=user.email,
        purpose="password reset",
        url=f"{settings.AUTH_PUBLIC_BASE_URL.rstrip('/')}/reset-password#token={token}",
    )
