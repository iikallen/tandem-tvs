import pytest
from django.test import override_settings
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.test import APIRequestFactory

from apps.identity import authentication
from apps.identity.authentication import PortalAuthentication
from apps.identity.managers import UserManager
from apps.identity.models import User
from apps.identity.portal.types import PortalEmployee, PortalIdentity, PortalOrgUnit
from apps.identity.services import sync_org_units
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
def test_adapter_cannot_substitute_a_different_employee(monkeypatch):
    class ConfusedAdapter:
        def authenticate_request(self, request):
            return PortalIdentity(portal_id="attacker-id")

        def get_employee(self, portal_id):
            return PortalEmployee(portal_id="victim-id", full_name="Victim", is_active=True)

    monkeypatch.setattr(authentication, "get_portal_adapter", ConfusedAdapter)

    with pytest.raises(AuthenticationFailed) as error:
        authenticate()

    assert error.value.get_codes() == "portal_identity_mismatch"
    assert not User.objects.exists()


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


@pytest.mark.django_db
def test_org_unit_sync_deactivates_omissions_and_reactivates_returned_units():
    OrgUnit.objects.create(external_id="stale", name="Старое подразделение")

    class SnapshotAdapter:
        def __init__(self, units):
            self.units = units

        def list_org_units(self):
            return self.units

    sync_org_units(
        SnapshotAdapter((PortalOrgUnit(external_id="company", name="Tandem", kind="company"),))
    )

    assert OrgUnit.objects.get(external_id="stale").is_active is False

    sync_org_units(
        SnapshotAdapter(
            (
                PortalOrgUnit(external_id="company", name="Tandem", kind="company"),
                PortalOrgUnit(
                    external_id="stale",
                    name="Возвращённое подразделение",
                    kind="department",
                    parent_external_id="company",
                ),
            )
        )
    )

    restored = OrgUnit.objects.get(external_id="stale")
    assert restored.is_active is True
    assert restored.name == "Возвращённое подразделение"
    assert restored.parent.external_id == "company"
