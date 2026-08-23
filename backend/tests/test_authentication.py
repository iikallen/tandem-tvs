import pytest
from django.test import override_settings
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.test import APIRequestFactory

from apps.identity.authentication import PortalAuthentication
from apps.identity.managers import UserManager
from apps.identity.models import User
from apps.organization.models import OrgUnit


def authenticate():
    request = APIRequestFactory().get("/api/v1/me")
    return PortalAuthentication().authenticate(request)


def create_user(**fields) -> User:
    manager = User.objects
    assert isinstance(manager, UserManager)
    return manager.create_user(**fields)


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="employee-1")
def test_active_employee_is_jit_provisioned_without_password():
    result = authenticate()
    assert result is not None

    user, identity = result
    assert identity.portal_id == "employee-1"
    assert user.portal_id == "employee-1"
    assert user.full_name == "Алия Байжанова"
    assert user.org_unit.external_id == "communications"
    assert user.module_roles == ["employee"]
    assert user.last_portal_sync_at is not None
    assert not user.has_usable_password()


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="blocked-1")
def test_blocked_employee_is_denied_and_existing_projection_is_deactivated():
    create_user(portal_id="blocked-1", full_name="Старое имя")

    with pytest.raises(PermissionDenied) as error:
        authenticate()

    assert error.value.get_codes() == "portal_account_blocked"
    assert User.objects.get(portal_id="blocked-1").is_active is False


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="unknown-1")
def test_unknown_employee_is_denied():
    with pytest.raises(AuthenticationFailed) as error:
        authenticate()
    assert error.value.get_codes() == "unknown_portal_identity"


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="")
def test_missing_identity_does_not_authenticate():
    assert authenticate() is None
    assert not User.objects.exists()


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="employee-1")
def test_each_request_refreshes_profile_and_organization_projection():
    user = create_user(
        portal_id="employee-1",
        full_name="Устаревшее имя",
        email="old@example.invalid",
    )

    authenticate()
    user.refresh_from_db()

    assert user.full_name == "Алия Байжанова"
    assert user.email == "a.baizhanova@tandem.example"
    assert user.org_unit.external_id == "communications"
    assert OrgUnit.objects.filter(external_id="company").exists()
    assert not user.has_usable_password()
