import json

from django.conf import settings
from pywebpush import WebPushException, webpush

from .models import PushSubscription


def send_wakeup(subscription: PushSubscription) -> str:
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps({}),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            timeout=10,
        )
        return "sent"
    except WebPushException as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code in {404, 410}:
            subscription.enabled = False
            subscription.save(update_fields=["enabled", "updated_at"])
            return "expired"
        raise
