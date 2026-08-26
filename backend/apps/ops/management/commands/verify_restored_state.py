import secrets

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from rest_framework.test import APIClient

from apps.identity.models import AccessGrant, User
from apps.messenger.models import Conversation, ConversationMembership, Message
from apps.notifications.models import Notification
from apps.publications.media import can_read_media
from apps.publications.models import MediaAsset, Publication


def _expect(response, status: int, label: str) -> None:
    if response.status_code != status:
        raise CommandError(f"Restored {label} smoke returned HTTP {response.status_code}")


def _verify_application_smoke() -> None:
    subject = (
        User.objects.filter(
            is_active=True,
            access_grants__module=AccessGrant.Module.NEWS,
            conversation_memberships__left_at__isnull=True,
        )
        .filter(access_grants__module=AccessGrant.Module.MESSENGER)
        .distinct()
        .first()
    )
    if subject is None:
        raise CommandError("Restored state has no active News + Messenger smoke user")
    membership = ConversationMembership.objects.filter(user=subject, left_at__isnull=True).first()
    readable_asset = next(
        (
            asset
            for asset in MediaAsset.objects.filter(status=MediaAsset.Status.READY).iterator()
            if can_read_media(subject, asset)
        ),
        None,
    )
    if membership is None or readable_asset is None:
        raise CommandError("Restored state has no authorized conversation/media smoke fixture")

    original_password = subject.password
    original_active = subject.is_active
    password = secrets.token_urlsafe(24)
    try:
        subject.set_password(password)
        subject.save(update_fields=["password"])
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/v1/auth/csrf")
        _expect(csrf, 200, "CSRF")
        token = csrf.data["csrf_token"]
        login = client.post(
            "/api/v1/auth/login",
            {"username": subject.username, "password": password},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        _expect(login, 200, "login")
        for path, label in (
            ("/api/v1/auth/session", "session"),
            ("/api/v1/news", "News"),
            ("/api/v1/messenger/conversations", "Messenger inbox"),
            (
                f"/api/v1/messenger/conversations/{membership.conversation.pk}/messages",
                "message history",
            ),
            ("/api/v1/search?q=restore", "search"),
            ("/api/v1/notifications", "notifications"),
            (f"/api/v1/media/{readable_asset.pk}/content", "protected media"),
        ):
            _expect(client.get(path), 200, label)

        subject.is_active = False
        subject.save(update_fields=["is_active"])
        denied = APIClient(enforce_csrf_checks=True)
        denied_csrf = denied.get("/api/v1/auth/csrf")
        _expect(denied_csrf, 200, "inactive-user CSRF")
        denied_login = denied.post(
            "/api/v1/auth/login",
            {"username": subject.username, "password": password},
            format="json",
            HTTP_X_CSRFTOKEN=denied_csrf.data["csrf_token"],
        )
        _expect(denied_login, 401, "inactive-user denial")
    finally:
        User.objects.filter(pk=subject.pk).update(
            password=original_password,
            is_active=original_active,
        )


class Command(BaseCommand):
    help = "Verify that a restore contains the core application state and protected media."

    def handle(self, *args, **options):
        checks = {
            "active users": User.objects.filter(is_active=True).exists(),
            "publications": Publication.objects.exists(),
            "conversations": Conversation.objects.exists(),
            "messages": Message.objects.exists(),
            "notifications": Notification.objects.exists(),
            "ready media": MediaAsset.objects.filter(status=MediaAsset.Status.READY).exists(),
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise CommandError("Restored state is incomplete: " + ", ".join(failed))
        call_command("verify_media_integrity")
        _verify_application_smoke()
        self.stdout.write("Restored application/API state: PASS")
