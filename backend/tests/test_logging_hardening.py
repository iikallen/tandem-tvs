import io
import json
import logging
import uuid

import pytest
from django.test import override_settings

from apps.core.logging import JsonFormatter
from apps.identity.models import User
from apps.notifications.delivery import deliver
from apps.notifications.models import Notification, NotificationDelivery


def _json_logger(stream: io.StringIO) -> logging.Logger:
    logger = logging.Logger("test.notification.delivery")
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger


def test_json_formatter_omits_exception_message_and_traceback():
    stream = io.StringIO()
    logger = _json_logger(stream)
    secret = "https://push.example.test/private recipient@example.test token=top-secret"

    try:
        raise ConnectionError(secret)
    except ConnectionError:
        logger.exception(
            "notification.delivery.failed",
            extra={"exception_code": "notification_delivery_failed"},
        )

    rendered = stream.getvalue()
    payload = json.loads(rendered)
    assert secret not in rendered
    assert payload["exception_class"] == "ConnectionError"
    assert payload["exception_code"] == "notification_delivery_failed"
    assert "exception" not in payload


@pytest.mark.django_db
@override_settings(NOTIFICATION_EMAIL_ENABLED=True)
def test_external_delivery_log_omits_endpoint_email_token_and_exception_details(monkeypatch):
    recipient = User.objects.create(
        username="logging-recipient",
        full_name="Logging Recipient",
        email="recipient@example.test",
    )
    notification = Notification.objects.create(
        recipient=recipient,
        notification_type=Notification.Type.ACK_REQUIRED,
        source_type="PUBLICATION",
        source_id=uuid.uuid4(),
        dedupe_key="logging-hardening",
    )
    delivery = NotificationDelivery.objects.create(
        notification=notification,
        channel=NotificationDelivery.Channel.EMAIL,
        event_version=1,
    )
    stream = io.StringIO()
    logger = _json_logger(stream)
    endpoint = "https://push.example.test/private"
    token = "top-secret-token"
    exception_message = f"endpoint={endpoint} email={recipient.email} token={token}"

    def fail_delivery(*_args, **_kwargs):
        raise ConnectionError(exception_message)

    monkeypatch.setattr("apps.notifications.delivery.logger", logger)
    monkeypatch.setattr("apps.notifications.delivery.send_mail", fail_delivery)

    assert deliver(delivery.pk) is False

    rendered = stream.getvalue()
    payload = json.loads(rendered)
    assert endpoint not in rendered
    assert recipient.email not in rendered
    assert token not in rendered
    assert exception_message not in rendered
    assert payload["message"] == "notification.delivery.failed"
    assert payload["exception_class"] == "ConnectionError"
    assert payload["exception_code"] == "notification_delivery_failed"
