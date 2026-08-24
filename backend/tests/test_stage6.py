import json
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.auth_services import (
    access_payload,
    activate_account,
    issue_invitation,
    issue_password_reset,
    request_ip,
    reset_password,
    validate_local_password,
)
from apps.identity.delivery import ConsoleAuthDelivery, SMTPAuthDelivery
from apps.identity.managers import UserManager
from apps.identity.models import (
    AccessGrant,
    AccountInvitation,
    AuthSecurityEvent,
    PasswordResetRequest,
    User,
)
from apps.publications.engagement import refresh_recipient_snapshot
from apps.publications.models import AudienceRule, Category, Publication

PASSWORD = "a long local passphrase for tandem"
NEW_PASSWORD = "another long local passphrase"


def user_manager() -> UserManager:
    manager = User.objects
    assert isinstance(manager, UserManager)
    return manager


def make_account(
    username: str = "member",
    *,
    password: str = PASSWORD,
    active: bool = True,
    grants: tuple[tuple[str, str], ...] = (("NEWS", "MEMBER"),),
) -> User:
    user = user_manager().create_user(
        username=username,
        password=password,
        full_name=username.title(),
        email=f"{username}@example.invalid",
        is_active=active,
    )
    user.activated_at = timezone.now()
    user.password_changed_at = user.activated_at
    user.save(update_fields=["activated_at", "password_changed_at", "updated_at"])
    AccessGrant.objects.bulk_create(
        [AccessGrant(user=user, module=module, role=role) for module, role in grants]
    )
    return user


def csrf(client: APIClient) -> str:
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return response.data["csrf_token"]


def login(client: APIClient, username: str = "member", password: str = PASSWORD):
    response = client.post(
        "/api/v1/auth/login",
        {"username": username, "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(client),
    )
    return response


@pytest.fixture(autouse=True)
def clear_auth_rate_limits():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_login_requires_csrf_uses_argon2_rotates_session_and_returns_fresh_token():
    user = make_account()
    client = APIClient(enforce_csrf_checks=True)

    assert (
        client.post(
            "/api/v1/auth/login",
            {"username": "member", "password": PASSWORD},
            format="json",
        ).status_code
        == 403
    )

    token = csrf(client)
    session_before = client.cookies[settings.SESSION_COOKIE_NAME].value
    response = client.post(
        "/api/v1/auth/login",
        {"username": "MEMBER", "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert response.status_code == 200
    assert response.data["user"]["username"] == "member"
    assert response.data["csrf_token"] != token
    assert client.cookies[settings.SESSION_COOKIE_NAME].value != session_before
    assert user.password.startswith("argon2$")
    assert client.get("/api/v1/auth/session").data["authenticated"] is True


@pytest.mark.django_db
def test_wrong_username_and_password_have_the_same_generic_denial():
    make_account()
    first = APIClient(enforce_csrf_checks=True)
    second = APIClient(enforce_csrf_checks=True)

    unknown = login(first, "unknown", "wrong password value")
    wrong = login(second, "member", "wrong password value")

    assert unknown.status_code == wrong.status_code == 401
    assert (
        unknown.data
        == wrong.data
        == {
            "error": {
                "code": "invalid_credentials",
                "message": "Invalid username or password.",
            }
        }
    )


@pytest.mark.django_db
def test_login_is_limited_per_username_and_ip():
    make_account()
    user_client = APIClient(enforce_csrf_checks=True)
    for _ in range(5):
        assert login(user_client, "member", "wrong password value").status_code == 401
    assert login(user_client, "member", "wrong password value").status_code == 429

    cache.clear()
    ip_client = APIClient(enforce_csrf_checks=True, REMOTE_ADDR="203.0.113.10")
    for index in range(20):
        assert login(ip_client, f"missing-{index}", "wrong password value").status_code == 401
    assert login(ip_client, "another-missing", "wrong password value").status_code == 429


@pytest.mark.django_db
def test_login_limiter_uses_the_validated_client_ip_forwarded_by_nginx():
    first = APIClient(
        enforce_csrf_checks=True,
        REMOTE_ADDR="172.29.0.5",
        HTTP_X_TANDEM_CLIENT_IP="198.51.100.10",
    )
    second = APIClient(
        enforce_csrf_checks=True,
        REMOTE_ADDR="172.29.0.5",
        HTTP_X_TANDEM_CLIENT_IP="198.51.100.11",
    )
    for index in range(20):
        assert login(first, f"proxy-missing-{index}", "wrong password value").status_code == 401
    assert login(first, "proxy-blocked", "wrong password value").status_code == 429
    assert login(second, "proxy-independent", "wrong password value").status_code == 401

    invalid = APIClient(REMOTE_ADDR="192.0.2.20", HTTP_X_TANDEM_CLIENT_IP="not-an-ip-address")
    assert request_ip(invalid.get("/api/v1/health/live").wsgi_request) == "192.0.2.20"


@pytest.mark.django_db
def test_inactive_no_grant_and_portal_header_users_are_denied():
    make_account(username="inactive", active=False)
    make_account(username="unentitled", grants=())

    assert login(APIClient(enforce_csrf_checks=True), "inactive").status_code == 401
    assert login(APIClient(enforce_csrf_checks=True), "unentitled").status_code == 401
    assert APIClient().get("/api/v1/me", HTTP_X_MOCK_PORTAL_USER="employee-1").status_code == 403


@pytest.mark.django_db
def test_logout_requires_csrf_and_clears_the_session():
    make_account()
    client = APIClient(enforce_csrf_checks=True)
    response = login(client)
    assert response.status_code == 200

    assert client.post("/api/v1/auth/logout").status_code == 403
    assert (
        client.post("/api/v1/auth/logout", HTTP_X_CSRFTOKEN=response.data["csrf_token"]).status_code
        == 204
    )
    assert client.get("/api/v1/auth/session").data == {
        "authenticated": False,
        "user": None,
    }


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["auth_started_at", "auth_last_seen_at"])
def test_idle_and_absolute_session_expiry(field):
    make_account()
    client = APIClient(enforce_csrf_checks=True)
    assert login(client).status_code == 200
    session = client.session
    session[field] = int((timezone.now() - timedelta(days=1)).timestamp())
    session.save()

    assert client.get("/api/v1/auth/session").data["authenticated"] is False


@pytest.mark.django_db
def test_password_policy_accepts_unicode_spaces_and_rejects_short_common_and_blocked():
    user = User(username="policy-user", full_name="Policy User")
    validate_local_password("ұзын құпия сөз бос орынмен", user)
    validate_local_password("phrase " * 16, user)

    for password in ("too short", "passwordpassword", "qwertyqwerty123"):
        with pytest.raises(ValidationError):
            validate_local_password(password, user)


@pytest.mark.django_db
def test_password_change_preserves_current_session_and_invalidates_other_sessions():
    make_account()
    current = APIClient(enforce_csrf_checks=True)
    other = APIClient(enforce_csrf_checks=True)
    current_login = login(current)
    assert current_login.status_code == 200
    assert login(other).status_code == 200

    rejected = current.post(
        "/api/v1/auth/password/change",
        {"current_password": "wrong current value", "new_password": NEW_PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=current_login.data["csrf_token"],
    )
    assert rejected.status_code == 400
    changed = current.post(
        "/api/v1/auth/password/change",
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(current),
    )
    assert changed.status_code == 204
    assert current.get("/api/v1/auth/session").data["authenticated"] is True
    assert other.get("/api/v1/auth/session").data["authenticated"] is False
    assert login(APIClient(enforce_csrf_checks=True), "member", NEW_PASSWORD).status_code == 200


@pytest.mark.django_db
def test_invitation_and_reset_tokens_are_hash_only_expiring_and_one_time(
    django_capture_on_commit_callbacks,
):
    actor = make_account(
        username="admin",
        grants=(("PLATFORM", "ADMIN"), ("NEWS", "ADMIN")),
    )
    pending = user_manager().create_user(username="pending", full_name="Pending")
    invitation, token = issue_invitation(pending, actor=actor)
    assert token not in invitation.token_hash
    assert token not in json.dumps(list(AccountInvitation.objects.values()), default=str)

    activated = activate_account(token, PASSWORD)
    assert activated.check_password(PASSWORD)
    AccessGrant.objects.create(
        user=activated, module=AccessGrant.Module.NEWS, role=AccessGrant.Role.MEMBER
    )
    with pytest.raises(ValidationError):
        activate_account(token, PASSWORD)

    reset, reset_token = issue_password_reset(activated, actor=actor)
    assert reset_token not in reset.token_hash
    active_session = APIClient(enforce_csrf_checks=True)
    assert login(active_session, activated.username, PASSWORD).status_code == 200
    with django_capture_on_commit_callbacks(execute=True):
        reset_password(reset_token, NEW_PASSWORD)
    assert active_session.get("/api/v1/auth/session").data["authenticated"] is False
    with pytest.raises(ValidationError):
        reset_password(reset_token, PASSWORD)

    expired_invitation, expired_token = issue_invitation(pending, actor=actor)
    AccountInvitation.objects.filter(pk=expired_invitation.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    with pytest.raises(ValidationError):
        activate_account(expired_token, PASSWORD)

    expired_reset, expired_reset_token = issue_password_reset(activated, actor=actor)
    PasswordResetRequest.objects.filter(pk=expired_reset.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    with pytest.raises(ValidationError):
        reset_password(expired_reset_token, PASSWORD)


@pytest.mark.django_db
def test_platform_admin_manages_entitlements_and_disabled_session_is_denied(
    django_capture_on_commit_callbacks,
):
    admin = make_account(
        username="admin",
        grants=(("PLATFORM", "ADMIN"), ("NEWS", "ADMIN")),
    )
    member = make_account(username="target", grants=(("NEWS", "MEMBER"),))
    admin_client = APIClient(enforce_csrf_checks=True)
    admin_login = login(admin_client, admin.username)
    assert admin_login.status_code == 200

    assert (
        admin_client.put(
            f"/api/v1/platform/users/{member.pk}/grants/MESSENGER/MEMBER",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=admin_login.data["csrf_token"],
        ).status_code
        == 204
    )
    member_client = APIClient(enforce_csrf_checks=True)
    assert login(member_client, member.username).status_code == 200
    assert member_client.get("/api/v1/messenger/access").data == {
        "allowed": True,
        "implementation": "stage-7",
    }

    with django_capture_on_commit_callbacks(execute=True):
        disabled = admin_client.patch(
            f"/api/v1/platform/users/{member.pk}",
            {"is_active": False},
            format="json",
            HTTP_X_CSRFTOKEN=csrf(admin_client),
        )
    assert disabled.status_code == 200
    assert member_client.get("/api/v1/auth/session").data["authenticated"] is False
    admin_client.patch(
        f"/api/v1/platform/users/{member.pk}",
        {"is_active": True},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(admin_client),
    )
    assert member_client.get("/api/v1/auth/session").data["authenticated"] is False


@pytest.mark.django_db
def test_security_events_are_append_only_and_do_not_store_credentials_or_tokens():
    user = make_account()
    client = APIClient(enforce_csrf_checks=True)
    assert login(client, password="incorrect secret phrase").status_code == 401
    assert login(client).status_code == 200
    event = AuthSecurityEvent.objects.filter(user=user).first()
    assert event is not None
    serialized = json.dumps(list(AuthSecurityEvent.objects.values()), default=str)
    assert PASSWORD not in serialized
    assert "incorrect secret phrase" not in serialized
    assert client.cookies[settings.SESSION_COOKIE_NAME].value not in serialized

    event.metadata = {"changed": True}
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        AuthSecurityEvent.objects.filter(pk=event.pk).update(event_type="tampered")
    with pytest.raises(ValidationError):
        AuthSecurityEvent.objects.filter(pk=event.pk).delete()


@pytest.mark.django_db
def test_full_platform_account_invitation_reset_and_grant_api():
    admin = make_account(
        username="platform-admin",
        grants=(("PLATFORM", "ADMIN"), ("NEWS", "ADMIN")),
    )
    client = APIClient(enforce_csrf_checks=True)
    signed_in = login(client, admin.username)
    assert signed_in.status_code == 200
    token = signed_in.data["csrf_token"]

    created = client.post(
        "/api/v1/platform/users",
        {
            "username": "New.User",
            "full_name": "New User",
            "email": "new.user@example.invalid",
            "job_title": "Writer",
            "phone": "+7 700 000 00 00",
            "grants": [
                {"module": "NEWS", "role": "MEMBER"},
                {"module": "MESSENGER", "role": "MEMBER"},
            ],
        },
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert created.status_code == 201
    user_id = created.data["id"]
    assert created.data["username"] == "new.user"
    assert created.data["access"]["messenger"] == ["MEMBER"]

    listed = client.get("/api/v1/platform/users", {"search": "New User"})
    assert [row["id"] for row in listed.data] == [user_id]
    assert client.get(f"/api/v1/platform/users/{user_id}").status_code == 200
    patched = client.patch(
        f"/api/v1/platform/users/{user_id}",
        {"job_title": "Senior Writer"},
        format="json",
        HTTP_X_CSRFTOKEN=csrf(client),
    )
    assert patched.data["job_title"] == "Senior Writer"

    assert (
        client.put(
            f"/api/v1/platform/users/{user_id}/grants/NEWS/AUTHOR",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf(client),
        ).status_code
        == 204
    )
    assert (
        client.delete(
            f"/api/v1/platform/users/{user_id}/grants/NEWS/AUTHOR",
            HTTP_X_CSRFTOKEN=csrf(client),
        ).status_code
        == 204
    )
    assert (
        client.put(
            f"/api/v1/platform/users/{user_id}/grants/PLATFORM/MEMBER",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf(client),
        ).status_code
        == 400
    )

    invitation = client.post(
        f"/api/v1/platform/users/{user_id}/invitation",
        HTTP_X_CSRFTOKEN=csrf(client),
    )
    assert invitation.status_code == 200
    activation_token = invitation.data["activation_url"].split("token=", 1)[1]
    activated = APIClient(enforce_csrf_checks=True)
    activation = activated.post(
        "/api/v1/auth/activate",
        {
            "token": activation_token,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
        format="json",
        HTTP_X_CSRFTOKEN=csrf(activated),
    )
    assert activation.status_code == 200

    reset = client.post(
        f"/api/v1/platform/users/{user_id}/password-reset",
        HTTP_X_CSRFTOKEN=csrf(client),
    )
    reset_token = reset.data["reset_url"].split("token=", 1)[1]
    reset_client = APIClient(enforce_csrf_checks=True)
    confirmed = reset_client.post(
        "/api/v1/auth/password/reset/confirm",
        {
            "token": reset_token,
            "password": NEW_PASSWORD,
            "password_confirm": NEW_PASSWORD,
        },
        format="json",
        HTTP_X_CSRFTOKEN=csrf(reset_client),
    )
    assert confirmed.status_code == 200
    assert authenticate(username="new.user", password=NEW_PASSWORD) is not None

    assert (
        client.patch(
            f"/api/v1/platform/users/{admin.pk}",
            {"is_active": False},
            format="json",
            HTTP_X_CSRFTOKEN=csrf(client),
        ).status_code
        == 400
    )
    assert (
        client.delete(
            f"/api/v1/platform/users/{admin.pk}/grants/PLATFORM/ADMIN",
            HTTP_X_CSRFTOKEN=csrf(client),
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_recovery_is_generic_and_smtp_delivery_is_adapter_driven(monkeypatch):
    user = make_account()
    delivered = []
    monkeypatch.setattr(
        "apps.identity.views.SMTPAuthDelivery.deliver",
        lambda self, **kwargs: delivered.append(kwargs),
    )
    client = APIClient(enforce_csrf_checks=True)

    with override_settings(AUTH_RECOVERY_MODE="SMTP"):
        known = client.post(
            "/api/v1/auth/password/reset/request",
            {"email": user.email},
            format="json",
            HTTP_X_CSRFTOKEN=csrf(client),
        )
        unknown = client.post(
            "/api/v1/auth/password/reset/request",
            {"email": "unknown@example.invalid"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf(client),
        )

    assert known.status_code == unknown.status_code == 200
    assert known.data == unknown.data
    assert delivered[0]["recipient"] == user.email
    assert "token=" in delivered[0]["url"]
    assert "token" not in json.dumps(known.data).casefold()


def test_delivery_adapters_and_manager_fail_closed(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "django.core.mail.send_mail",
        lambda **kwargs: sent.append(kwargs),
    )
    assert (
        ConsoleAuthDelivery().deliver(
            recipient="nobody@example.invalid", purpose="test", url="https://example.invalid"
        )
        is None
    )
    SMTPAuthDelivery().deliver(
        recipient="member@example.invalid",
        purpose="password reset",
        url="https://example.invalid/reset",
    )
    assert sent[0]["recipient_list"] == ["member@example.invalid"]
    with pytest.raises(NotImplementedError):
        user_manager().create_superuser(username="root", password=PASSWORD)


@pytest.mark.django_db
def test_access_payload_has_stable_empty_modules_and_role_ordering():
    user = make_account(grants=(("NEWS", "EDITOR"), ("NEWS", "AUTHOR")))
    assert access_payload(user) == {
        "platform": [],
        "news": ["AUTHOR", "EDITOR"],
        "messenger": [],
    }


@pytest.mark.django_db
def test_local_account_without_portal_id_can_be_snapshotted_as_recipient():
    user = make_account(username="local-recipient")
    category = Category.objects.create(slug="local-recipient", name="Local recipient")
    publication = Publication.objects.create(
        title="Local recipient",
        slug="local-recipient",
        summary="Stage 6 recipient compatibility",
        body={"type": "doc", "content": []},
        category=category,
        author=user,
        status=Publication.Status.PUBLISHED,
        published_at=timezone.now(),
    )
    AudienceRule.objects.create(publication=publication, kind=AudienceRule.Kind.ALL)

    rows = refresh_recipient_snapshot(publication)

    assert len(rows) == 1
    assert rows[0].user == user
    assert rows[0].portal_id == ""
