"""Two-phase Stage 6 acceptance for local identity and restart-safe sessions."""

import json
import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.sessions.models import Session  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.utils import timezone  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from apps.identity.auth_services import (  # noqa: E402
    activate_account,
    fingerprint,
    issue_invitation,
    issue_password_reset,
    reset_password,
)
from apps.identity.models import (  # noqa: E402
    AccessGrant,
    AccountInvitation,
    PasswordResetRequest,
    User,
)
from apps.organization.models import OrgUnit  # noqa: E402

STATE_FILE = Path(settings.MEDIA_ROOT) / ".stage6-session-fingerprint.json"
USERNAME = "stage6-acceptance"
NEW_PASSWORD = "Stage six changed passphrase 2026"
PUBLICATION_ID = "00000000-0000-0000-0000-000000003001"


def csrf(client: APIClient) -> str:
    response = client.get(
        "/api/v1/auth/csrf", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
    )
    assert response.status_code == 200, response.data
    return response.data["csrf_token"]


def login(client: APIClient, username: str, password: str):
    return client.post(
        "/api/v1/auth/login",
        {"username": username, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(client),
        HTTP_HOST="localhost",
        HTTP_X_FORWARDED_PROTO="https",
    )


def acceptance_user(actor: User) -> User:
    if not settings.STAGE6_DEMO_PASSWORD:
        raise RuntimeError("STAGE6_DEMO_PASSWORD is required")
    user, _ = User.objects.get_or_create(
        username=USERNAME,
        defaults={
            "full_name": "Stage 6 Acceptance",
            "email": "stage6-acceptance@example.invalid",
        },
    )
    user.is_active = True
    user.org_unit = OrgUnit.objects.get(external_id="communications")
    user.set_unusable_password()
    user.activated_at = None
    user.password_changed_at = None
    user.save(
        update_fields=[
            "is_active",
            "org_unit",
            "password",
            "activated_at",
            "password_changed_at",
            "updated_at",
        ]
    )
    AccessGrant.objects.filter(user=user).delete()
    _invitation, token = issue_invitation(user, actor=actor)
    activated = activate_account(token, settings.STAGE6_DEMO_PASSWORD)
    AccessGrant.objects.create(
        user=activated,
        module=AccessGrant.Module.NEWS,
        role=AccessGrant.Role.MEMBER,
        created_by=actor,
    )
    return activated


def prepare() -> None:
    call_command("seed_stage2_demo", verbosity=0)
    call_command("seed_stage3_demo", verbosity=0)
    actor = User.objects.get(portal_id="admin-1")
    user = acceptance_user(actor)
    client = APIClient(enforce_csrf_checks=True)
    signed_in = login(client, user.username, settings.STAGE6_DEMO_PASSWORD)
    assert signed_in.status_code == 200, signed_in.data
    session_key = client.cookies[settings.SESSION_COOKIE_NAME].value
    assert session_key
    assert client.get(
        "/api/v1/auth/session", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
    ).data["authenticated"]
    assert (
        client.get(
            "/api/v1/news", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/v1/messenger/access", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
        ).status_code
        == 403
    )
    ticket = client.post(
        "/api/v1/realtime/tickets",
        {"publication_id": PUBLICATION_ID},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(client),
        HTTP_HOST="localhost",
        HTTP_X_FORWARDED_PROTO="https",
    )
    assert ticket.status_code == 200, ticket.data
    anonymous_ticket = APIClient(enforce_csrf_checks=True).post(
        "/api/v1/realtime/tickets",
        {"publication_id": PUBLICATION_ID},
        format="json",
        HTTP_HOST="localhost",
        HTTP_X_FORWARDED_PROTO="https",
    )
    assert anonymous_ticket.status_code in {401, 403}
    bypass = APIClient().get(
        "/api/v1/me",
        HTTP_X_MOCK_PORTAL_USER="admin-1",
        HTTP_HOST="localhost",
        HTTP_X_FORWARDED_PROTO="https",
    )
    assert bypass.status_code in {401, 403}
    user.refresh_from_db()
    assert user.password.startswith("argon2$")
    STATE_FILE.write_text(
        json.dumps({"user_id": user.pk, "session_fingerprint": fingerprint(session_key)}),
        encoding="utf-8",
    )
    print(json.dumps({"phase": "prepare", "status": "PASS", "user_id": user.pk}))


def persisted_client() -> tuple[APIClient, User]:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    user = User.objects.get(pk=state["user_id"])
    for row in Session.objects.filter(expire_date__gt=timezone.now()):
        decoded = row.get_decoded()
        if (
            str(decoded.get("_auth_user_id")) == str(user.pk)
            and fingerprint(row.session_key) == state["session_fingerprint"]
        ):
            client = APIClient(enforce_csrf_checks=True)
            client.cookies[settings.SESSION_COOKIE_NAME] = row.session_key
            return client, user
    raise AssertionError("Prepared authenticated session did not survive restart")


def verify() -> None:
    client, user = persisted_client()
    session = client.get(
        "/api/v1/auth/session", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
    )
    assert session.status_code == 200 and session.data["authenticated"] is True

    second = APIClient(enforce_csrf_checks=True)
    assert login(second, user.username, settings.STAGE6_DEMO_PASSWORD).status_code == 200
    changed = client.post(
        "/api/v1/auth/password/change",
        {
            "current_password": settings.STAGE6_DEMO_PASSWORD,
            "new_password": NEW_PASSWORD,
        },
        format="json",
        HTTP_X_CSRFTOKEN=csrf(client),
        HTTP_HOST="localhost",
        HTTP_X_FORWARDED_PROTO="https",
    )
    assert changed.status_code == 204, changed.data
    assert client.get(
        "/api/v1/auth/session", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
    ).data["authenticated"]
    assert not second.get(
        "/api/v1/auth/session", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
    ).data["authenticated"]
    fresh = APIClient(enforce_csrf_checks=True)
    assert login(fresh, user.username, NEW_PASSWORD).status_code == 200
    assert (
        fresh.get("/api/v1/news", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https").status_code
        == 200
    )
    assert (
        fresh.get(
            "/api/v1/messenger/access", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
        ).status_code
        == 403
    )

    actor = User.objects.get(portal_id="admin-1")
    pending, _ = User.objects.get_or_create(
        username="stage6-pending",
        defaults={"full_name": "Stage 6 Pending", "email": "pending@example.invalid"},
    )
    pending.is_active = True
    pending.set_unusable_password()
    pending.save(update_fields=["is_active", "password", "updated_at"])
    invitation, invitation_token = issue_invitation(pending, actor=actor)
    activate_account(invitation_token, settings.STAGE6_DEMO_PASSWORD)
    try:
        activate_account(invitation_token, settings.STAGE6_DEMO_PASSWORD)
        raise AssertionError("Invitation replay was accepted")
    except ValidationError:
        pass
    expired, expired_token = issue_invitation(pending, actor=actor)
    AccountInvitation.objects.filter(pk=expired.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    try:
        activate_account(expired_token, settings.STAGE6_DEMO_PASSWORD)
        raise AssertionError("Expired invitation was accepted")
    except ValidationError:
        pass
    reset, reset_token = issue_password_reset(pending, actor=actor)
    reset_password(reset_token, NEW_PASSWORD)
    try:
        reset_password(reset_token, NEW_PASSWORD)
        raise AssertionError("Reset replay was accepted")
    except ValidationError:
        pass
    expired_reset, expired_reset_token = issue_password_reset(pending, actor=actor)
    PasswordResetRequest.objects.filter(pk=expired_reset.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    try:
        reset_password(expired_reset_token, NEW_PASSWORD)
        raise AssertionError("Expired reset was accepted")
    except ValidationError:
        pass

    admin = APIClient(enforce_csrf_checks=True)
    assert login(admin, actor.username, settings.STAGE6_DEMO_PASSWORD).status_code == 200
    disabled = admin.patch(
        f"/api/v1/platform/users/{user.pk}",
        {"is_active": False},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(admin),
        HTTP_HOST="localhost",
        HTTP_X_FORWARDED_PROTO="https",
    )
    assert disabled.status_code == 200, disabled.data
    assert not fresh.get(
        "/api/v1/auth/session", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
    ).data["authenticated"]
    enabled = admin.patch(
        f"/api/v1/platform/users/{user.pk}",
        {"is_active": True},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(admin),
        HTTP_HOST="localhost",
        HTTP_X_FORWARDED_PROTO="https",
    )
    assert enabled.status_code == 200, enabled.data
    assert not fresh.get(
        "/api/v1/auth/session", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
    ).data["authenticated"]

    for role in (
        AccessGrant.Role.AUTHOR,
        AccessGrant.Role.EDITOR,
        AccessGrant.Role.MODERATOR,
        AccessGrant.Role.ADMIN,
    ):
        response = admin.put(
            f"/api/v1/platform/users/{user.pk}/grants/NEWS/{role}",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf(admin),
            HTTP_HOST="localhost",
            HTTP_X_FORWARDED_PROTO="https",
        )
        assert response.status_code == 204, response.data
    messenger_grant = admin.put(
        f"/api/v1/platform/users/{user.pk}/grants/MESSENGER/MEMBER",
        {},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(admin),
        HTTP_HOST="localhost",
        HTTP_X_FORWARDED_PROTO="https",
    )
    assert messenger_grant.status_code == 204, messenger_grant.data

    restored = APIClient(enforce_csrf_checks=True)
    restored_login = login(restored, user.username, NEW_PASSWORD)
    assert restored_login.status_code == 200, restored_login.data
    assert set(restored_login.data["user"]["access"]["news"]) == {
        "MEMBER",
        "AUTHOR",
        "EDITOR",
        "MODERATOR",
        "ADMIN",
    }
    assert (
        restored.get(
            "/api/v1/messenger/access", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
        ).status_code
        == 200
    )
    logged_out = restored.post(
        "/api/v1/auth/logout",
        format="json",
        HTTP_X_CSRFTOKEN=csrf(restored),
        HTTP_HOST="localhost",
        HTTP_X_FORWARDED_PROTO="https",
    )
    assert logged_out.status_code == 204
    assert not restored.get(
        "/api/v1/auth/session", HTTP_HOST="localhost", HTTP_X_FORWARDED_PROTO="https"
    ).data["authenticated"]

    user.is_active = False
    user.save(update_fields=["is_active", "updated_at"])
    pending.is_active = False
    pending.save(update_fields=["is_active", "updated_at"])
    STATE_FILE.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "phase": "verify",
                "status": "PASS",
                "redis_restart_session": True,
                "backend_restart_session": True,
                "other_session_invalidated": True,
                "disabled_session_denied": True,
            }
        )
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "verify"
    {"prepare": prepare, "verify": verify}[mode]()
